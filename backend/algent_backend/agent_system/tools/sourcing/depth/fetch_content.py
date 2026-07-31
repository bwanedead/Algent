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
5. **optional Playwright** — JS render, OFF by default (``ALGENT_FETCH_PLAYWRIGHT=1``
   to enable). Heavy on low-end machines; skip until you want to test it.
6. **Firecrawl** — hosted fallback for JS-heavy / bot-walled pages, attempted only
   when the free result isn't ``good`` *and* a key is set *and* the caller allows
   paid escalation (``allow_paid_fallback``).

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


def _playwright_html(url: str) -> str | None:
    """Optional JS render. Soft-fails when playwright is missing or browsers aren't installed."""
    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        return None
    try:
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True)
            try:
                page = browser.new_page()
                page.goto(url, wait_until="domcontentloaded", timeout=int(_TIMEOUT_S * 1000))
                # Brief settle for late JSON-LD / article hydration without a long wait.
                page.wait_for_timeout(800)
                return page.content()
            finally:
                browser.close()
    except Exception:
        return None


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

    Returns ``{url, content, via, quality, words, meta?}``. ``via`` is the engine that
    won; ``quality`` is ``good`` | ``thin`` | ``blocked`` | ``empty``. Set
    ``allow_paid_fallback=False`` to stay free-only for low-value pages.
    """
    cached = _cache_get(url)
    if cached and cached.get("quality") == "good":
        return cached

    html = _http_get(url)
    content, via, quality, words, meta = _grade_html(html)
    content, via, quality, words, meta = _maybe_playwright_rescue(
        url, content, via, quality, words, meta,
    )
    content, via, quality, words = _maybe_firecrawl_rescue(
        url, content, via, quality, words, meta, allow_paid_fallback,
    )

    if not content:
        raise RuntimeError(
            f"Could not extract content from {url} "
            "(free fetch empty/blocked; Playwright/Firecrawl unavailable, disallowed, or empty)."
        )
    result = {
        "url": url,
        "content": content[:_MAX_CHARS],
        "via": via,
        "quality": quality,
        "words": words,
    }
    if meta:
        result["meta"] = meta
    if quality == "good":
        _cache_put(url, result)
    return result


def _maybe_playwright_rescue(url, content, via, quality, words, meta):
    if quality == "good" or not _playwright_enabled():
        return content, via, quality, words, meta
    rendered = _playwright_html(url)
    if not rendered:
        return content, via, quality, words, meta
    p_content, _, p_quality, p_words, p_meta = _grade_html(rendered, meta)
    if _better_candidate(
        new_quality=p_quality, new_words=p_words,
        old_quality=quality, old_words=words,
    ):
        return p_content, "playwright", p_quality, p_words, p_meta
    return content, via, quality, words, meta


def _maybe_firecrawl_rescue(url, content, via, quality, words, meta, allow_paid):
    if quality == "good" or not allow_paid:
        return content, via, quality, words
    api_key = get_service_api_key("firecrawl")
    if not api_key:
        return content, via, quality, words
    rescued = _firecrawl_markdown(url, api_key)
    r_quality, r_words = _quality(rescued, meta)
    if _better_candidate(
        new_quality=r_quality, new_words=r_words,
        old_quality=quality, old_words=words,
    ):
        return rescued, "firecrawl", r_quality, r_words
    return content, via, quality, words


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
