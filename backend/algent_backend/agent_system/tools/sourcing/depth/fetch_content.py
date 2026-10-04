"""
``fetch_content`` — full-page article extraction with a cheap-first ladder.

Search returns ~200-char snippets; depth comes from reading the page. The bulk of
news/article pages are server-rendered HTML, so we can read them for free and
well — and only spend on the minority that genuinely need a managed crawler. The
ladder, cheapest first:

1. **httpx fetch** with realistic browser headers.
2. **metadata / JSON-LD** — titles, descriptions, and citation fields often survive
   even when the visible body is a podcast shell or JS shell.
3. **trafilatura** extraction — precision pass, then a recall pass if it's thin.
4. **quality scoring** — completeness (not word count alone) decides whether the
   free result is trustworthy (``good``) or needs rescue.
5. **Jina Reader** — free, keyless rendered-page markdown (``via: "jina"``).
6. **Wayback** — newest Internet Archive snapshot (``via: "wayback"``, adds ``archived_at``).
7. **optional Playwright** — JS render, OFF by default (``ALGENT_FETCH_PLAYWRIGHT=1``).
8. **Firecrawl** — hosted fallback for JS-heavy / bot-walled pages, attempted only
   when the free result isn't ``good`` *and* a key is set *and* the caller allows
   paid escalation (``allow_paid_fallback``).

Rungs 5-7 live in ``free_rungs.py`` (pacing, privacy, cost notes there). A later rung never runs once
one reaches ``good``; ``not_found`` stops everything. Each read is logged to ``read_ledger``.

Every result reports ``via`` (which engine won) and ``quality`` so the agent
knows how much to trust the content. Playwright is never a hard dependency —
missing install or env-off simply skips that rung.

Firecrawl API: POST https://api.firecrawl.dev/v1/scrape {"url","formats":
["markdown"]} — verify the response shape on first live probe.
"""

from __future__ import annotations

import hashlib
import json
import os
import re
import time
from pathlib import Path
from typing import Any

from algent_backend.config import get_service_api_key

from ...spec import GLOBAL_SCOPE, ToolSpec
from .._wrap import as_structured_tool
from . import read_ledger
from .free_rungs import jina_markdown as _jina_markdown
from .free_rungs import playwright_html as _playwright_html
from .free_rungs import wayback_html as _wayback_html

FETCH_CONTENT_TOOL_ID = "fetch_content"

_FIRECRAWL_ENDPOINT = "https://api.firecrawl.dev/v1/scrape"
_TIMEOUT_S = 30.0
_MAX_CHARS = 40_000  # keep one page from flooding a prompt
_MIN_GOOD_WORDS = 120  # raised: ~80-word podcast blurbs used to false-"good"
_MIN_PARTIAL_WORDS = 40
_PLAYWRIGHT_ENV = "ALGENT_FETCH_PLAYWRIGHT"
_CACHE_ENV = "ALGENT_FETCH_CACHE"
_CACHE_TTL_S = 6 * 3600  # six hours — enough to stop same-run thrash, not forever

# A real browser fingerprint clears the bulk of lazy bot-blocks for free.
_BROWSER_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/123.0.0.0 Safari/537.36"
    ),
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.9",
}

# Markers of a wall rather than an article — only damning on a *short* body
# (a real article *about* captchas would be long, so length guards false hits).
_WALL_MARKERS = (
    "enable javascript",
    "are you a robot",
    "are you a human",
    "verify you are human",
    "access denied",
    "captcha",
    "please enable cookies",
    "subscribe to continue",
    "this site requires javascript",
)

_JSONLD_RE = re.compile(
    r'<script[^>]+type=["\']application/ld\+json["\'][^>]*>(.*?)</script>',
    re.I | re.S,
)
_OG_TITLE_RE = re.compile(
    r'<meta[^>]+property=["\']og:title["\'][^>]+content=["\']([^"\']+)["\']',
    re.I,
)
_OG_DESC_RE = re.compile(
    r'<meta[^>]+property=["\']og:description["\'][^>]+content=["\']([^"\']+)["\']',
    re.I,
)
_META_DESC_RE = re.compile(
    r'<meta[^>]+name=["\']description["\'][^>]+content=["\']([^"\']+)["\']',
    re.I,
)
_CITATION_DOI_RE = re.compile(
    r'<meta[^>]+name=["\']citation_doi["\'][^>]+content=["\']([^"\']+)["\']',
    re.I,
)
_TITLE_TAG_RE = re.compile(r"<title[^>]*>(.*?)</title>", re.I | re.S)


def _playwright_enabled() -> bool:
    return os.environ.get(_PLAYWRIGHT_ENV, "0").strip().lower() in ("1", "true", "yes", "on")


def _cache_enabled() -> bool:
    # ON by default — free disk; disable with ALGENT_FETCH_CACHE=0.
    return os.environ.get(_CACHE_ENV, "1").strip().lower() in ("1", "true", "yes", "on")


def _cache_dir() -> Path:
    override = os.environ.get("ALGENT_FETCH_CACHE_DIR", "").strip()
    if override:
        return Path(override)
    # backend/.cache/fetch — walk up until we find the package root marker.
    here = Path(__file__).resolve()
    for parent in here.parents:
        if (parent / "algent_backend").is_dir() and (parent / "requirements.txt").is_file():
            return parent / ".cache" / "fetch"
    return here.parent / ".cache" / "fetch"


def _cache_get(url: str) -> dict[str, Any] | None:
    if not _cache_enabled():
        return None
    path = _cache_dir() / f"{hashlib.sha256(url.encode()).hexdigest()}.json"
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    if time.time() - float(raw.get("cached_at") or 0) > _CACHE_TTL_S:
        return None
    payload = raw.get("payload")
    return payload if isinstance(payload, dict) else None


def _cache_put(url: str, payload: dict[str, Any]) -> None:
    if not _cache_enabled():
        return
    try:
        d = _cache_dir()
        d.mkdir(parents=True, exist_ok=True)
        path = d / f"{hashlib.sha256(url.encode()).hexdigest()}.json"
        path.write_text(
            json.dumps({"url": url, "cached_at": time.time(), "payload": payload}),
            encoding="utf-8",
        )
    except OSError:
        pass


class PageNotFound(RuntimeError):
    """The page definitively does not exist (404/410, or the host does not resolve).

    Distinct from a bot wall: a wall may yield to a better crawler, a missing page never will,
    so this must stop the ladder instead of escalating to a paid fetch.
    """


_NOT_FOUND_FIX = "find the real URL by searching (site:domain …); do not construct URLs"
_DNS_MARKERS = (
    "getaddrinfo", "name or service not known", "nodename nor servname",
    "temporary failure in name resolution", "no address associated",
)


def _is_dns_failure(exc: Exception) -> bool:
    import socket

    import httpx

    if isinstance(exc, httpx.InvalidURL):
        return True
    chain, seen = exc, 0
    while chain is not None and seen < 5:
        if isinstance(chain, socket.gaierror) or any(
            m in str(chain).lower() for m in _DNS_MARKERS
        ):
            return True
        chain, seen = chain.__cause__ or chain.__context__, seen + 1
    return False


def _unreadable_reason(url: str) -> str | None:
    """Why ``url`` can never be fetched, without trying (and without any paid escalation)."""
    low = url.lower()
    if "webcache.googleusercontent.com" in low:
        return "Google's web cache was shut down; these links are dead — search for the live page instead"
    if "*" in url:
        return "wildcard (*) URLs are not fetchable pages — search for the real page URL instead"
    return None


def _http_get(url: str) -> str | None:
    """Fetch raw HTML with browser headers; None on block/error/other non-200.

    Raises ``PageNotFound`` on 404/410 and on DNS/invalid-host failure — the cases where the
    URL itself is wrong, which the agent must hear about (it usually means a guessed URL).
    """
    import httpx

    try:
        response = httpx.get(
            url, headers=_BROWSER_HEADERS, timeout=_TIMEOUT_S, follow_redirects=True
        )
    except Exception as exc:
        if _is_dns_failure(exc):
            raise PageNotFound(
                f"host does not resolve (DNS failure) — {_NOT_FOUND_FIX}"
            ) from exc
        return None
    if response.status_code in (404, 410):
        raise PageNotFound(
            f"page does not exist (HTTP {response.status_code}) — {_NOT_FOUND_FIX}"
        )
    return response.text if response.status_code == 200 else None


_JSONLD_ARTICLE_TYPES = (
    "article", "newsarticle", "scholarlyarticle", "webpage", "blogposting",
)


def _extract_meta(html: str) -> dict[str, str]:
    """Pull title/description/DOI from JSON-LD + common meta tags (stdlib only)."""
    meta: dict[str, str] = {}
    for block in _JSONLD_RE.findall(html or ""):
        try:
            data = json.loads(block.strip())
        except json.JSONDecodeError:
            continue
        nodes = data if isinstance(data, list) else [data]
        for node in nodes:
            if isinstance(node, dict):
                _absorb_jsonld_node(meta, node)
    _absorb_html_meta_tags(meta, html or "")
    return meta


def _absorb_html_meta_tags(meta: dict[str, str], html: str) -> None:
    if "title" not in meta:
        m = _OG_TITLE_RE.search(html) or _TITLE_TAG_RE.search(html)
        if m:
            meta["title"] = re.sub(r"\s+", " ", m.group(1)).strip()
    if "description" not in meta:
        m = _OG_DESC_RE.search(html) or _META_DESC_RE.search(html)
        if m:
            meta["description"] = m.group(1).strip()
    if "doi" not in meta:
        m = _CITATION_DOI_RE.search(html)
        if m:
            meta["doi"] = m.group(1).strip()


def _absorb_jsonld_node(meta: dict[str, str], node: dict[str, Any]) -> None:
    typ = node.get("@type") or ""
    types = typ if isinstance(typ, list) else [typ]
    type_l = " ".join(str(t).lower() for t in types)
    if any(k in type_l for k in _JSONLD_ARTICLE_TYPES):
        if node.get("headline") and "title" not in meta:
            meta["title"] = str(node["headline"])
        if node.get("name") and "title" not in meta:
            meta["title"] = str(node["name"])
        if node.get("description") and "description" not in meta:
            meta["description"] = str(node["description"])
        if node.get("doi") and "doi" not in meta:
            meta["doi"] = str(node["doi"])
    cite = node.get("citation")
    if isinstance(cite, dict) and cite.get("doi") and "doi" not in meta:
        meta["doi"] = str(cite["doi"])
    same = node.get("sameAs")
    if isinstance(same, str) and "doi.org/" in same and "doi" not in meta:
        meta["doi"] = same.split("doi.org/", 1)[-1]


def _extract(html: str) -> str | None:
    """trafilatura precision pass, then a recall pass if the result is thin."""
    import trafilatura

    content = trafilatura.extract(html, include_comments=False)
    if content and len(content.split()) >= _MIN_GOOD_WORDS:
        return content
    recalled = trafilatura.extract(html, include_comments=False, favor_recall=True)
    # Keep whichever recovered more text.
    candidates = [c for c in (content, recalled) if c]
    return max(candidates, key=lambda c: len(c.split())) if candidates else None


def _merge_meta_into_content(content: str | None, meta: dict[str, str]) -> str | None:
    """Prefixed metadata can rescue a thin body and surfaces DOI for scholarly follow-up."""
    parts: list[str] = []
    if meta.get("title"):
        parts.append(f"Title: {meta['title']}")
    if meta.get("doi"):
        parts.append(f"DOI: {meta['doi']}")
    if meta.get("description") and (
        not content or meta["description"].lower() not in content.lower()
    ):
        parts.append(meta["description"])
    if content:
        parts.append(content)
    if not parts:
        return None
    return "\n\n".join(parts)


def _firecrawl_markdown(url: str, api_key: str) -> str | None:
    import httpx

    response = httpx.post(
        _FIRECRAWL_ENDPOINT,
        json={"url": url, "formats": ["markdown"]},
        headers={"Authorization": f"Bearer {api_key}"},
        timeout=_TIMEOUT_S,
    )
    response.raise_for_status()
    return response.json().get("data", {}).get("markdown") or None


def _looks_walled(content: str) -> bool:
    head = content[:2000].lower()
    return any(marker in head for marker in _WALL_MARKERS)


def _looks_incomplete(content: str, meta: dict[str, str]) -> bool:
    """Word count alone is not enough — podcast shells and JS stubs look 'long enough'.

    Incomplete when: short relative to a rich meta description, or the body barely
    overlaps the page title (extracted a nav/chrome fragment, not the article).
    """
    words = len(content.split())
    desc = meta.get("description") or ""
    title = meta.get("title") or ""
    if desc and len(desc.split()) >= 40 and words < len(desc.split()) * 1.5 and words < 200:
        # Body shorter than / barely longer than the meta blurb → we got the blurb, not the piece.
        return True
    if title and words < 200:
        tokens = [t.lower() for t in re.findall(r"[A-Za-z]{4,}", title)]
        if tokens:
            body_l = content.lower()
            hits = sum(1 for t in tokens if t in body_l)
            if hits / len(tokens) < 0.3:
                return True
    return False


def _quality(content: str | None, meta: dict[str, str] | None = None) -> tuple[str, int]:
    """Grade extracted content: (label, word_count). label decides escalation."""
    meta = meta or {}
    if not content or not content.strip():
        return "empty", 0
    words = len(content.split())
    if words < _MIN_PARTIAL_WORDS:
        return ("blocked" if _looks_walled(content) else "empty"), words
    if words < _MIN_GOOD_WORDS:
        return ("blocked" if _looks_walled(content) else "thin"), words
    if _looks_incomplete(content, meta):
        return "thin", words
    return "good", words


_QUALITY_RANK = {"good": 3, "thin": 2, "blocked": 1, "empty": 0}


def _better_candidate(
    *,
    new_quality: str, new_words: int,
    old_quality: str, old_words: int,
) -> bool:
    """Prefer higher extraction quality; break ties with useful length."""
    nq, oq = _QUALITY_RANK.get(new_quality, 0), _QUALITY_RANK.get(old_quality, 0)
    if nq != oq:
        return nq > oq
    return new_words > old_words


def _grade_html(html: str | None, fallback_meta: dict[str, str] | None = None) -> tuple[
    str | None, str, str, int, dict[str, str],
]:
    """(content, via, quality, words, meta) from one HTML snapshot."""
    meta = _extract_meta(html) if html else {}
    if fallback_meta:
        meta = {**fallback_meta, **meta}
    body = _extract(html) if html else None
    content = _merge_meta_into_content(body, meta)
    via = "trafilatura" if body else ("meta" if content else "none")
    quality, words = _quality(content, meta)
    return content, via, quality, words, meta


def _fetch(url: str, allow_paid_fallback: bool = True) -> dict[str, Any]:
    """Extract readable article content from ``url`` via the cheap-first ladder.

    Returns ``{url, content, via, quality, words, meta?}``, or ``{url, error, not_found: True}``
    when the page does not exist / cannot be fetched at all (never escalated to paid). ``via`` is the engine that
    won; ``quality`` is ``good`` | ``thin`` | ``blocked`` | ``empty``. Wayback results add
    ``archived_at`` and a ``hint`` (the text may predate the live page). Set
    ``allow_paid_fallback=False`` to stay free-only for low-value pages. Every non-cached read
    appends one line to the read ledger.
    """
    cached = _cache_get(url)
    if cached and cached.get("quality") == "good":
        return cached
    reason = _unreadable_reason(url)
    if reason:
        return {"url": url, "error": reason, "not_found": True}

    started, rungs = time.monotonic(), ["http"]
    outcome: dict[str, Any] = {"via": "none", "quality": "empty", "not_found": False}
    try:
        result = _run_ladder(url, allow_paid_fallback, rungs)
    except PageNotFound as gone:
        outcome["not_found"] = True
        # A missing page is a final answer: no JS render, no paid crawler, no retry hint.
        return {"url": url, "error": str(gone), "not_found": True}
    else:
        outcome.update(via=result["via"], quality=result["quality"])
        return result
    finally:
        read_ledger.record(url, rungs=rungs, elapsed_ms=int((time.monotonic() - started) * 1000), **outcome)


def _run_ladder(url: str, allow_paid_fallback: bool, rungs: list[str]) -> dict[str, Any]:
    html = _http_get(url)  # may raise PageNotFound
    content, via, quality, words, meta = _grade_html(html)
    best = (content, via, quality, words, meta)
    extra: dict[str, Any] = {}

    def consider(name: str, cand: tuple | None, add: dict[str, Any] | None = None) -> None:
        """Adopt ``cand`` (content, quality, words, meta) if it beats the best so far."""
        nonlocal best, extra
        if cand is None or not cand[0]:
            return
        c, q, w, m = cand
        if _better_candidate(new_quality=q, new_words=w, old_quality=best[2], old_words=best[3]):
            best, extra = (c, name, q, w, m), (add or {})

    for name, attempt in _free_rungs(url, lambda: best[4]):
        if best[2] == "good":
            break
        rungs.append(name)
        got = attempt()
        if name == "wayback" and got:
            consider(name, got[0], got[1])
        else:
            consider(name, got)
    if best[2] != "good" and allow_paid_fallback:
        api_key = get_service_api_key("firecrawl")
        if api_key:
            rungs.append("firecrawl")
            rescued = _firecrawl_markdown(url, api_key)
            r_quality, r_words = _quality(rescued, best[4])
            consider("firecrawl", (rescued, r_quality, r_words, best[4]))

    content, via, quality, words, meta = best
    if not content:
        raise RuntimeError(
            f"Could not extract content from {url} "
            "(free fetch empty/blocked; Jina/Wayback/Playwright/Firecrawl unavailable, disallowed, or empty)."
        )
    result = {
        "url": url,
        "content": content[:_MAX_CHARS],
        "via": via,
        "quality": quality,
        "words": words,
        **extra,
    }
    if meta:
        result["meta"] = meta
    if quality == "good":
        _cache_put(url, result)
    return result


def _free_rungs(url: str, meta_now):
    """(name, attempt) in ladder order; each attempt returns (content, quality, words, meta) or None."""

    def jina():
        md = _jina_markdown(url)
        q, w = _quality(md, meta_now())
        return (md, q, w, meta_now()) if md else None

    def wayback():
        snap = _wayback_html(url)
        if not snap:
            return None
        content, _, q, w, m = _grade_html(snap[0], meta_now())
        stamp = snap[1]
        note = {"archived_at": stamp, "hint": (
            f"read from an Internet Archive snapshot taken {stamp[:4]}-{stamp[4:6]}-{stamp[6:8]}; "
            "the live page may differ or be newer")}
        return (content, q, w, m), note

    def playwright():
        rendered = _playwright_html(url)
        if not rendered:
            return None
        content, _, q, w, m = _grade_html(rendered, meta_now())
        return content, q, w, m

    yield "jina", jina
    yield "wayback", wayback
    if _playwright_enabled():
        yield "playwright", playwright


def _build() -> Any:
    return as_structured_tool(
        _fetch,
        name="fetch_content",
        description=(
            "Fetches a URL and extracts the readable article content as text, "
            "free-first with optional Playwright (ALGENT_FETCH_PLAYWRIGHT=1) and a paid "
            "Firecrawl fallback for hard pages. Returns the content plus a 'quality' grade "
            "and which engine was used. Pass allow_paid_fallback=false for low-value pages "
            "to stay free-only."
        ),
    )


SPEC = ToolSpec(
    tool_id=FETCH_CONTENT_TOOL_ID,
    name="fetch_content",
    description="Extracts full readable content from a web page (beyond search snippets).",
    scope=GLOBAL_SCOPE,
    build=_build,
    channel="depth",
)
