"""
``xai_x_search`` — live X (Twitter) search through xAI's Grok live-search API.

Named ``xai_x_search`` (not ``x_search``) on purpose: it is the *Grok-mediated*,
derived-intelligence view of X — Grok searches X server-side and reports back
with citations. It is deliberately distinct from future canonical ``x_api_*``
tools (raw post objects from the X REST API) and from a future ``grok_build``
external-agent rail. The name encodes the trust level: derived, not canonical.

X has no affordable direct search API, but xAI exposes Grok with server-side live
search over X. So this tool is a model-call-in-tool's-clothing: it asks a Grok
model to search X for a query and report what it finds. That is also why it uses
the *provider* key (XAI_API_KEY), not a service key — the same credential that
would power Grok as a chat model.

API (verified against xAI docs 2026-06): POST /v1/chat/completions with
``search_parameters`` — mode, sources [{"type": "x"}], return_citations,
from_date/to_date. Pricing is per-source-searched; verify on first live probe.
"""

from __future__ import annotations

from typing import Any

from algent_backend.config import get_provider_api_key

from ...spec import GLOBAL_SCOPE, ToolSpec
from .._wrap import as_structured_tool

XAI_X_SEARCH_TOOL_ID = "xai_x_search"

_ENDPOINT = "https://api.x.ai/v1/chat/completions"
# Cheap/fast Grok variant — the tool is a search reporter, not a deep reasoner.
_MODEL = "grok-4-fast"
_TIMEOUT_S = 60.0

_REPORT_INSTRUCTION = (
    "Search X for posts about the query. Report the notable posts, claims, and "
    "sentiment you find. Be factual and specific; attribute claims to their "
    "posters; note disagreement where it exists. Do not add your own opinion."
)


def _search(query: str, max_results: int = 10) -> dict[str, Any]:
    """Search X via Grok live search; returns {report, citations}."""
    import httpx

    api_key = get_provider_api_key("xai")
    if not api_key:
        raise RuntimeError("xai_x_search requires XAI_API_KEY (see backend/.env.example).")

    payload = {
        "model": _MODEL,
        "messages": [
            {"role": "system", "content": _REPORT_INSTRUCTION},
            {"role": "user", "content": query},
        ],
        "search_parameters": {
            "mode": "on",
            "sources": [{"type": "x"}],
            "return_citations": True,
            "max_search_results": max_results,
        },
    }
    response = httpx.post(
        _ENDPOINT,
        json=payload,
        headers={"Authorization": f"Bearer {api_key}"},
        timeout=_TIMEOUT_S,
    )
    response.raise_for_status()
    body = response.json()

    message = body.get("choices", [{}])[0].get("message", {})
    return {
        "report": message.get("content", ""),
        "citations": body.get("citations", []),
    }


def _build() -> Any:
    return as_structured_tool(
        _search,
        name="xai_x_search",
        description=(
            "Searches X (Twitter) live via xAI Grok and reports notable posts, "
            "claims, and sentiment with citations."
        ),
    )


SPEC = ToolSpec(
    tool_id=XAI_X_SEARCH_TOOL_ID,
    name="xai_x_search",
    description="Live X (Twitter) search via xAI Grok: posts, claims, sentiment, citations.",
    scope=GLOBAL_SCOPE,
    build=_build,
    channel="social",
)
