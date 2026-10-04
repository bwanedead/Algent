"""
``ddg`` — keyless keyword web search over DuckDuckGo's HTML endpoint (the free tier).

Why this exists: the paid keyword engines (Tavily, Brave) are quota-starved or unconfigured, and
an agent with no way to FIND pages starts GUESSING them — measured, 77% of page reads in recent
runs hit URLs the model invented. A free literal index that supports ``site:domain`` closes that
gap: the agent can locate the real page on a named site instead of constructing one.

Reached with plain ``httpx`` + ``lxml`` — no SDK, no key. Result links are DuckDuckGo redirects
that carry the true destination in a ``uddg=`` parameter, so the real URL is decoded out of them;
ad units (``duckduckgo.com/y.js`` redirects, ``result--ad`` blocks) are dropped.

Politeness and failure shape: DDG tolerates modest traffic and answers abuse with a challenge page
(often HTTP 202) rather than an error code. That challenge is raised as a "rate limit" error so
``circuit.py`` opens the breaker and the facade falls through to the next engine, instead of the
agent quietly receiving "no results" for a query that was merely blocked.
"""

from __future__ import annotations

import threading
import time
from typing import Any
from urllib.parse import parse_qs, urlparse

_ENDPOINT = "https://html.duckduckgo.com/html/"
_TIMEOUT_S = 15.0
#: Process-wide gap between DDG requests. Agents fan out in parallel threads and the news
#: resolver issues several queries back to back; blocks followed bursts (a challenge page that then
#: lasts many minutes), so we trade a little latency for a slow, steady trickle DDG does not mistake
#: for a scraper.
_MIN_INTERVAL_S = 2.5
_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/123.0.0.0 Safari/537.36"
    ),
    "Accept": "text/html,application/xhtml+xml",
    "Accept-Language": "en-US,en;q=0.9",
}
#: Text DDG serves in place of results when it wants a human. Lower-case substring match.
_CHALLENGE_MARKERS = ("anomaly", "unusual traffic", "bots use duckduckgo", "select all squares")

_pace_lock = threading.Lock()
_last_request = 0.0


def _pace() -> None:
    """Block until at least ``_MIN_INTERVAL_S`` has passed since the last DDG request."""
    global _last_request
    with _pace_lock:
        wait = _MIN_INTERVAL_S - (time.monotonic() - _last_request)
        if wait > 0:
            time.sleep(wait)
        _last_request = time.monotonic()


def _real_url(href: str) -> str | None:
    """The destination behind a DDG redirect link; None for ads and unusable links."""
    if not href:
        return None
    if href.startswith("//"):
        href = "https:" + href
    parsed = urlparse(href)
    if parsed.netloc.endswith("duckduckgo.com"):
        if parsed.path.startswith("/y.js"):  # ad click-tracker
            return None
        target = parse_qs(parsed.query).get("uddg")
        href = target[0] if target else ""
    return href if href.startswith(("http://", "https://")) else None


def _is_challenge(body: str) -> bool:
    low = body.lower()
    return any(m in low for m in _CHALLENGE_MARKERS)


def parse_results(html: str) -> list[dict[str, str]]:
    """Parse a DDG HTML results page into ``[{title, url, content}]`` (deduped, ads dropped)."""
    from lxml import html as lxml_html

    if not html.strip():
        return []
    doc = lxml_html.fromstring(html)
    hits: list[dict[str, str]] = []
    seen: set[str] = set()
    for block in doc.xpath('//div[contains(@class, "result") and .//a[@class="result__a"]]'):
        if "result--ad" in (block.get("class") or ""):
            continue
        link = block.xpath('.//a[@class="result__a"]')[0]
        url = _real_url(link.get("href", ""))
        if not url or url in seen:
            continue
        seen.add(url)
        snippet = block.xpath('.//*[contains(@class, "result__snippet")]')
        hits.append({
            "title": link.text_content().strip(),
            "url": url,
            "content": snippet[0].text_content().strip() if snippet else "",
        })
    return hits


def search(query: str, max_results: int = 10) -> list[dict[str, str]]:
    """Search DuckDuckGo and return ``[{title, url, content}]`` — the shape every provider uses.

    Raises on HTTP errors and on a challenge page, always with "rate limit" in the text so the
    circuit breaker treats a block as a provider outage rather than an empty answer.
    """
    import httpx

    _pace()
    response = httpx.get(
        _ENDPOINT, params={"q": query}, headers=_HEADERS,
        timeout=_TIMEOUT_S, follow_redirects=True,
    )
    # Judge by what came back, not by words alone: a snippet may legitimately say "anomaly", so
    # a challenge is only declared when the page carries no results at all.
    hits = parse_results(response.text) if response.status_code == 200 else []
    if hits:
        return hits[:max_results]
    if response.status_code in (202, 403, 418, 429) or _is_challenge(response.text):
        raise RuntimeError(
            f"duckduckgo rate limit: challenge/anomaly response (HTTP {response.status_code})"
        )
    response.raise_for_status()
    return []
