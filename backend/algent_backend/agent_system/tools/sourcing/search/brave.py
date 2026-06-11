"""
``brave_search`` — keyword web search against Brave's independent index.

Brave maintains its own index (not Google/Bing-derived), so it adds genuine
result diversity next to Tavily. Reached over plain REST with ``httpx`` — no
extra SDK — and wrapped as a StructuredTool for a uniform ``.invoke`` surface.

API: GET https://api.search.brave.com/res/v1/web/search (X-Subscription-Token).
Free tier available; key name BRAVE_API_KEY.
"""

from __future__ import annotations

from typing import Any

from algent_backend.config import get_service_api_key

from ...spec import GLOBAL_SCOPE, ToolSpec
from .._wrap import as_structured_tool

BRAVE_SEARCH_TOOL_ID = "brave_search"

_ENDPOINT = "https://api.search.brave.com/res/v1/web/search"
_TIMEOUT_S = 15.0


def _search(query: str, max_results: int = 5) -> list[dict[str, str]]:
    """Search Brave and return [{title, url, description}, ...]."""
    import httpx

    api_key = get_service_api_key("brave")
    if not api_key:
        raise RuntimeError("brave_search requires BRAVE_API_KEY (see backend/.env.example).")

    response = httpx.get(
        _ENDPOINT,
        params={"q": query, "count": max_results},
        headers={"X-Subscription-Token": api_key, "Accept": "application/json"},
        timeout=_TIMEOUT_S,
    )
    response.raise_for_status()
    payload = response.json()

    results = payload.get("web", {}).get("results", [])
    return [
        {
            "title": item.get("title", ""),
            "url": item.get("url", ""),
            "description": item.get("description", ""),
        }
        for item in results[:max_results]
    ]


def _build() -> Any:
    return as_structured_tool(
        _search,
        name="brave_search",
        description="Searches the web (Brave's independent index) for results on a query.",
    )


SPEC = ToolSpec(
    tool_id=BRAVE_SEARCH_TOOL_ID,
    name="brave_search",
    description="Searches the web via Brave's independent index for result diversity.",
    scope=GLOBAL_SCOPE,
    build=_build,
    channel="search",
)
