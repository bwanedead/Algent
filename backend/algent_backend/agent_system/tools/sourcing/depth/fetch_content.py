"""
``fetch_content`` — full-page article extraction with a cheap-first ladder.

Search returns ~200-char snippets; depth comes from reading the page. The bulk of
news/article pages are server-rendered HTML, so we can read them for free and
well — and only spend on the minority that genuinely need a managed crawler. The
ladder, cheapest first:

1. **httpx fetch** with realistic browser headers — many sites 403 a bare
   fetcher; a normal UA + Accept headers clears most of that for free.
2. **trafilatura** extraction — precision pass, then a recall pass if it's thin.
3. **quality scoring** — word count + bot/JS/paywall-wall detection decide whether
   the free result is trustworthy (``good``) or needs rescue.
4. **Firecrawl** — hosted fallback for JS-heavy / bot-walled pages, attempted only
   when the free result isn't ``good`` *and* a key is set *and* the caller allows
   paid escalation (``allow_paid_fallback``). That last switch is the budget rail:
   the agent passes ``False`` for low-value bulk and ``True`` for sources worth a
   credit.

Every result reports ``via`` (which engine won) and ``quality`` so the agent
knows how much to trust the content. No headless browser here on purpose — that
tier is memory-heavy and deferred; Firecrawl covers the JS/anti-bot minority.

Firecrawl API: POST https://api.firecrawl.dev/v1/scrape {"url","formats":
["markdown"]} — verify the response shape on first live probe.
"""

from __future__ import annotations

from typing import Any

from algent_backend.config import get_service_api_key

from ...spec import GLOBAL_SCOPE, ToolSpec
from .._wrap import as_structured_tool

FETCH_CONTENT_TOOL_ID = "fetch_content"

_FIRECRAWL_ENDPOINT = "https://api.firecrawl.dev/v1/scrape"
_TIMEOUT_S = 30.0
_MAX_CHARS = 40_000  # keep one page from flooding a prompt
_MIN_GOOD_WORDS = 80  # below this an article body is "thin", not trustworthy

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


def _http_get(url: str) -> str | None:
    """Fetch raw HTML with browser headers; None on block/error/non-200."""
    import httpx

    try:
        response = httpx.get(
            url, headers=_BROWSER_HEADERS, timeout=_TIMEOUT_S, follow_redirects=True
        )
    except Exception:
        return None
    return response.text if response.status_code == 200 else None


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


def _quality(content: str | None) -> tuple[str, int]:
    """Grade extracted content: (label, word_count). label decides escalation."""
    if not content or not content.strip():
        return "empty", 0
    words = len(content.split())
    if words >= _MIN_GOOD_WORDS:
        return "good", words
    return ("blocked" if _looks_walled(content) else "thin"), words


def _fetch(url: str, allow_paid_fallback: bool = True) -> dict[str, Any]:
    """Extract readable article content from ``url`` via the cheap-first ladder.

    Returns ``{url, content, via, quality, words}``. ``via`` is the engine that
    won (``trafilatura`` | ``firecrawl``); ``quality`` is ``good`` | ``thin`` |
    ``blocked`` | ``empty`` — read it to judge how much to trust the text. Set
    ``allow_paid_fallback=False`` to stay free-only for low-value pages.
    """
    html = _http_get(url)
    content = _extract(html) if html else None
    via = "trafilatura"
    quality, words = _quality(content)

    if quality != "good" and allow_paid_fallback:
        api_key = get_service_api_key("firecrawl")
        if api_key:
            rescued = _firecrawl_markdown(url, api_key)
            r_quality, r_words = _quality(rescued)
            if r_words > words:  # only adopt the rescue if it recovered more
                content, via, quality, words = rescued, "firecrawl", r_quality, r_words

    if not content:
        raise RuntimeError(
            f"Could not extract content from {url} "
            "(free fetch empty/blocked; Firecrawl unavailable, disallowed, or empty)."
        )
    return {
        "url": url,
        "content": content[:_MAX_CHARS],
        "via": via,
        "quality": quality,
        "words": words,
    }


def _build() -> Any:
    return as_structured_tool(
        _fetch,
        name="fetch_content",
        description=(
            "Fetches a URL and extracts the readable article content as text, "
            "free-first with a paid Firecrawl fallback for hard pages. Returns the "
            "content plus a 'quality' grade and which engine was used. Pass "
            "allow_paid_fallback=false for low-value pages to stay free-only."
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
