"""
``semantic_search`` — neural/semantic search via LangChain's Exa integration.

Exa searches by meaning rather than keywords ("essays critical of X written by
economists" works), which makes it the niche-and-subtle-angle finder in the
portfolio — the channel keyword engines cannot replace.

Only this module imports ``langchain_exa``. Key name EXA_API_KEY.
"""

from __future__ import annotations

from typing import Any

from algent_backend.config import get_service_api_key

from ...spec import GLOBAL_SCOPE, ToolSpec

SEMANTIC_SEARCH_TOOL_ID = "semantic_search"


def _build() -> Any:
    """Construct the Exa search tool. Called when a run actually needs it."""
    from langchain_exa import ExaSearchResults

    kwargs: dict[str, Any] = {}
    api_key = get_service_api_key("exa")
    if api_key:
        kwargs["exa_api_key"] = api_key
    return ExaSearchResults(**kwargs)


SPEC = ToolSpec(
    tool_id=SEMANTIC_SEARCH_TOOL_ID,
    name="semantic_search",
    description=("Semantic (meaning-based) web search for niche or hard-to-keyword content."),
    scope=GLOBAL_SCOPE,
    build=_build,
    channel="search",
)
