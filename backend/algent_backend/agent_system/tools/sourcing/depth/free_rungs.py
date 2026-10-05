"""
Free rescue rungs for ``fetch_content`` — what we try before paying Firecrawl.

Each rung takes a URL and returns raw material (markdown or HTML) or ``None``; grading and
ordering stay in ``fetch_content._fetch``. Ladder position: after httpx+trafilatura, in this order
``jina`` -> ``wayback`` -> ``playwright`` (opt-in) -> paid.

* **Jina Reader** (``https://r.jina.ai/<url>``): keyless, returns markdown of a browser-rendered
  page, so it substitutes for most of what Firecrawl is paid for. Privacy: Jina (a third party)
  sees the URL — fine, we only read public pages. Free tier is ~20 requests/minute without a key,
  so reads are spaced process-wide by ``_JINA_MIN_INTERVAL_S`` (3.2s => <=18.75/min). Set
  ``ALGENT_JINA_KEY`` for a Bearer key and higher limits (never required). Their error and limit
  pages are returned as failure, never as content.
* **Wayback**: the Internet Archive's newest snapshot (``id_`` raw form, no toolbar). The text may
  be OLDER than the live page, so the caller must report ``archived_at`` to the agent.
* **Playwright** (``ALGENT_FETCH_PLAYWRIGHT=1``, OFF by default, optional import): real JS render.
  Cost: Chromium is ~150-300 MB on disk and ~200-400 MB RAM while a page is open. We keep it
  light: one page at a time (process-wide lock), images/media/fonts/stylesheets blocked, short
  navigation timeout, and the whole browser is closed after EACH read. Install (operator only):
  ``pip install playwright`` then ``python -m playwright install chromium``. The ledger
  (``newsroom reads``) shows how many reads only this rung rescued — the evidence for installing.
"""

from __future__ import annotations

import os
import re
import threading
import time

_JINA_ENDPOINT = "https://r.jina.ai/"
_JINA_KEY_ENV = "ALGENT_JINA_KEY"
_JINA_TIMEOUT_S = 25.0  # Jina renders the page itself; keep the wait bounded
_JINA_MIN_INTERVAL_S = 3.2  # free tier ~20 req/min => 3.0s apart; 0.2s of headroom
_WAYBACK_API = "https://archive.org/wayback/available"
_WAYBACK_TIMEOUT_S = 12.0
_WAYBACK_MIN_INTERVAL_S = 4.0  # archive.org 429s a burst of availability calls; stay polite
_PLAYWRIGHT_NAV_TIMEOUT_MS = 20_000
_PLAYWRIGHT_BLOCKED = {"image", "media", "font", "stylesheet"}

_UA = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/123.0.0.0 Safari/537.36"
    ),
}

# Jina answers failures with a normal-looking body; these markers in its head mean "not content".
_JINA_FAILURE_MARKERS = (
    "target url returned error",
    "requiring captcha",
    "rate limit",
    "too many requests",
    "authenticationrequirederror",
    "insufficient balance",
    "securitycompromiseerror",
    "this domain has been blocked",
    "\"code\":4", "\"code\":5",
)
# Jina prefixes "Title: / URL Source: / Warning: ..." lines (blank-line separated) before the body.
_JINA_HEADER_RE = re.compile(r"\A.{0,800}?^Markdown Content:[ \t]*\n?", re.I | re.S | re.M)

_pace_lock = threading.Lock()
_next_at: dict[str, float] = {}
_playwright_lock = threading.Lock()


def _pace(service: str, interval_s: float) -> None:
    """Process-wide spacing: block until ``interval_s`` has passed since this service's last call."""
    with _pace_lock:
        wait = _next_at.get(service, 0.0) - time.monotonic()
        if wait > 0:
            time.sleep(wait)
        _next_at[service] = time.monotonic() + interval_s


def jina_markdown(url: str) -> str | None:
    """Markdown of the rendered page via Jina Reader; ``None`` on any failure or limit page."""
    import httpx

    # No browser-UA spoofing: Jina's Cloudflare 403s a Chrome UA on a non-browser TLS stack
    # (measured), while the plain httpx identity is served.
    headers = {"Accept": "text/plain", "X-Return-Format": "markdown"}
    key = os.environ.get(_JINA_KEY_ENV, "").strip()
    if key:
        headers["Authorization"] = f"Bearer {key}"
    _pace("jina", _JINA_MIN_INTERVAL_S)
    try:
        response = httpx.get(
            _JINA_ENDPOINT + url, headers=headers, timeout=_JINA_TIMEOUT_S, follow_redirects=True,
        )
    except Exception:  # noqa: BLE001 — a rescue rung never raises
        return None
    if response.status_code != 200:
        return None
    text = response.text or ""
    if any(m in text[:600].lower() for m in _JINA_FAILURE_MARKERS):
        return None
    return _JINA_HEADER_RE.sub("", text, count=1).strip() or None


def wayback_html(url: str) -> tuple[str, str] | None:
    """(raw archived HTML, snapshot timestamp YYYYMMDDhhmmss) for the newest snapshot, or None.

    archive.org answers a burst with 429 for minutes. A 429 opens the shared provider breaker (doubling
    cooldown, the same rule the search engines use), so a run stops asking until it lifts instead of
    extending the block with every read."""
    import httpx

    from ..search import circuit

    if circuit.is_open("wayback"):
        return None
    _pace("wayback", _WAYBACK_MIN_INTERVAL_S)
    try:
        meta = httpx.get(
            _WAYBACK_API, params={"url": url}, headers=_UA, timeout=_WAYBACK_TIMEOUT_S,
        )
        if meta.status_code == 429:
            circuit.record_failure("wayback", "429 rate limit")
            return None
        circuit.record_success("wayback")
        closest = (meta.json().get("archived_snapshots") or {}).get("closest") or {}
        stamp = str(closest.get("timestamp") or "")
        if meta.status_code != 200 or not closest.get("available") or not stamp.isdigit():
            return None
        snap = httpx.get(
            f"https://web.archive.org/web/{stamp}id_/{url}",
            headers=_UA, timeout=_WAYBACK_TIMEOUT_S * 2, follow_redirects=True,
        )
    except Exception:  # noqa: BLE001
        return None
    return (snap.text, stamp) if snap.status_code == 200 and snap.text else None


def playwright_html(url: str) -> str | None:
    """Optional JS render; soft-fails when playwright or its browser is not installed."""
    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        return None
    with _playwright_lock:  # one page at a time keeps the laptop's RAM bounded
        try:
            with sync_playwright() as p:
                browser = p.chromium.launch(headless=True)
                try:
                    page = browser.new_page()
                    page.route(
                        "**/*",
                        lambda route: route.abort()
                        if route.request.resource_type in _PLAYWRIGHT_BLOCKED
                        else route.continue_(),
                    )
                    page.goto(url, wait_until="domcontentloaded", timeout=_PLAYWRIGHT_NAV_TIMEOUT_MS)
                    page.wait_for_timeout(800)  # brief settle for hydration, not a long wait
                    return page.content()
                finally:
                    browser.close()  # never keep a browser resident between reads
        except Exception:  # noqa: BLE001
            return None
