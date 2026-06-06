"""
Global ``web_search`` tool, backed by LangChain's Tavily integration.

This is the only place ``langchain_tavily`` is imported (lazily, inside the
builder), keeping the rail dependency out of the neutral tool layer. The API key
comes from Algent's config layer, not a scattered ``os.getenv``.
"""

from __future__ import annotations

from typing import Any

from algent_backend.config import get_service_api_key

from ..spec import GLOBAL_SCOPE, ToolSpec

WEB_SEARCH_TOOL_ID = "web_search"

_MAX_RESULTS = 5
# Tavily supports "general" | "news" | "finance"; news suits Algent's first agent.
_TOPIC = "news"


def _build() -> Any:
    """Construct the Tavily search tool. Called when a run actually needs it."""
    from langchain_tavily import TavilySearch

    kwargs: dict[str, Any] = {"max_results": _MAX_RESULTS, "topic": _TOPIC}
    api_key = get_service_api_key("tavily")
    if api_key:
        kwargs["tavily_api_key"] = api_key
    return TavilySearch(**kwargs)


SPEC = ToolSpec(
    tool_id=WEB_SEARCH_TOOL_ID,
    # snake_case so it is safe to expose directly to LLM tool-calling later,
    # where provider tool schemas expect snake_case names.
    name="web_search",
    description="Searches the web for recent, relevant results on a query.",
    scope=GLOBAL_SCOPE,
    build=_build,
)
