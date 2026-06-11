"""
``fetch_content`` — full-page article extraction, with cost escalation.

Search returns ~200-char snippets; depth comes from reading the page. One tool
id, two engines behind it:

1. trafilatura — local, free, fast; handles most article pages.
2. Firecrawl — hosted fallback for JS-heavy or bot-walled pages. Only attempted
   when trafilatura comes back empty *and* FIRECRAWL_API_KEY is configured.

Firecrawl API: POST https://api.firecrawl.dev/v1/scrape {"url", "formats":
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


def _via_trafilatura(url: str) -> str | None:
    import trafilatura

    downloaded = trafilatura.fetch_url(url)
    if not downloaded:
        return None
    return trafilatura.extract(downloaded, include_comments=False)


def _via_firecrawl(url: str, api_key: str) -> str | None:
    import httpx

    response = httpx.post(
        _FIRECRAWL_ENDPOINT,
        json={"url": url, "formats": ["markdown"]},
        headers={"Authorization": f"Bearer {api_key}"},
        timeout=_TIMEOUT_S,
    )
    response.raise_for_status()
    data = response.json().get("data", {})
    return data.get("markdown") or None


def _fetch(url: str) -> dict[str, str]:
    """Extract readable article content from a URL; returns {url, content, via}."""
    content = _via_trafilatura(url)
    via = "trafilatura"

    if not content:
        api_key = get_service_api_key("firecrawl")
        if api_key:
            content = _via_firecrawl(url, api_key)
            via = "firecrawl"

    if not content:
        raise RuntimeError(
            f"Could not extract content from {url} "
            "(trafilatura found nothing; Firecrawl unavailable or empty)."
        )
    return {"url": url, "content": content[:_MAX_CHARS], "via": via}


def _build() -> Any:
    return as_structured_tool(
        _fetch,
        name="fetch_content",
        description="Fetches a URL and extracts the readable article content as text.",
    )


SPEC = ToolSpec(
    tool_id=FETCH_CONTENT_TOOL_ID,
    name="fetch_content",
    description="Extracts full readable content from a web page (beyond search snippets).",
    scope=GLOBAL_SCOPE,
    build=_build,
    channel="depth",
)
