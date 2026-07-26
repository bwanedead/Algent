"""
``web_search`` — the agent's single research surface (a cost-aware facade).

One tool, several capabilities behind cost-disciplined parameters, so the agent
reasons in INTENTS — keyword vs semantic, snippets vs rich, search vs read — and
never juggles provider-named tools (Tavily/Exa/Firecrawl are implementation
details hidden in here). Cheap-first by construction (see the paid-api-sparingly
ethos): free/snippet results by default; paid escalation (full-content fetch via
Firecrawl, or X) happens only when the agent deliberately asks for it.

Capabilities, by parameter:
- **search the web** — ``web_search(query, kind="keyword"|"semantic")``. Keyword
  routes to Tavily, semantic to Exa; the agent picks by intent, not vendor.
- **read a page** — ``web_search(read_url="https://…")``; free extraction by
  default, ``richness="rich"`` permits the paid Firecrawl fallback for hard pages.
- **X** — ``web_search(query, source="x")``; live X search. A DIFFERENT SOURCE CLASS (the
  people inside a story post there before the wires digest it), not a fallback for a failed read.

Guardrails: ``max_results`` is hard-capped; ``rich`` and ``x`` require a
deliberate choice; the read path stays free unless ``richness="rich"``. The usual
flow is cheap: search for snippets, then ``read_url`` the one result worth the
full read.
"""

from __future__ import annotations

from typing import Any

from ....foundation import cost, snapshots
from ...spec import GLOBAL_SCOPE, ToolSpec
from .._wrap import as_structured_tool
from . import policy

WEB_SEARCH_TOOL_ID = "web_search"

_MAX_RESULTS_CAP = 10  # hard ceiling so a call can't fan out into a credit drain


def _denied(channel: str) -> dict[str, Any]:
    return {
        "error": f"channel '{channel}' is not permitted for this agent",
        "permitted_channels": sorted(policy.allowed()),
    }


def _budget_exhausted(channel: str) -> dict[str, Any]:
    return {
        "error": f"paid-call budget exhausted for this run (channel '{channel}')",
        "remaining_paid_budget": 0,
    }


def _cost_capped(channel: str) -> dict[str, Any]:
    return {
        "error": f"run cost cap reached; paid channel '{channel}' refused",
        "remaining_usd": round(cost.remaining_usd(), 4),
    }


def _spend_paid(channel: str) -> dict[str, Any] | None:
    """Try to authorize one paid call: count budget AND dollar cap. None = OK."""
    est = cost.estimate_call_cost(channel)
    if cost.would_exceed(est):
        return _cost_capped(channel)
    if not policy.try_spend_paid():
        return _budget_exhausted(channel)
    cost.add(est)
    return None


def _search(
    query: str = "",
    kind: str = "keyword",
    read_url: str = "",
    richness: str = "standard",
    source: str = "web",
    max_results: int = 5,
) -> dict[str, Any]:
    """Investigate the web through one cost-aware surface. See the module docstring.

    - ``query`` + ``kind`` ("keyword"|"semantic"): search the web.
    - ``read_url``: read that page instead (``richness="rich"`` allows paid Firecrawl).
    - ``source="x"``: LIVE X SEARCH — real posts, available now. Use it when a story is unfolding,
      when you need what someone ACTUALLY posted rather than an outlet's characterization of it,
      or when the wires agree and you need to know if anyone credible on the ground disputes them.
    """
    max_results = max(1, min(max_results, _MAX_RESULTS_CAP))

    if read_url:
        rich = richness == "rich"
        # Reading always needs READ; the paid Firecrawl fallback also needs RICH
        # and spends one paid-budget unit (deliberate, capped).
        if not policy.is_allowed(policy.READ):
            return _denied(policy.READ)
        if rich:
            if not policy.is_allowed(policy.RICH):
                return _denied(policy.RICH)
            refusal = _spend_paid(policy.RICH)
            if refusal is not None:
                return refusal
        return _read(read_url, rich=rich)

    if source == "x":
        if not policy.is_allowed(policy.X):
            return _denied(policy.X)
        # Pre-authorize on the default estimate; then true-up to posts actually returned.
        refusal = _spend_paid(policy.X)
        if refusal is not None:
            return refusal
        from .x_search import x_recent_search
        from algent_backend.agent_system.foundation import cost as run_cost
        payload = x_recent_search(query, max_results)
        results = payload.get("results") or []
        # True-up: we already charged estimate_call_cost("x"); adjust to posts × $0.005.
        assumed = run_cost.estimate_call_cost(policy.X)
        actual = run_cost.estimate_x_posts(len(results) if isinstance(results, list) else 0)
        delta = actual - assumed
        if abs(delta) > 1e-9:
            run_cost.add(delta)
        return {
            "action": "search", "kind": "x",
            "estimated_usd": round(actual, 6),
            "posts": len(results) if isinstance(results, list) else 0,
            **payload,
        }

    channel = policy.SEMANTIC if kind == "semantic" else policy.KEYWORD
    if not policy.is_allowed(channel):
        return _denied(channel)
    return _search_web(query, kind, max_results)


def _read(url: str, *, rich: bool) -> dict[str, Any]:
    """Read a page via the free-first fetch ladder (paid only when ``rich``).

    Two honest signals accompany a read so the agent (and doctrine) can act:
    - ``retry_hint`` on a *degraded free* read — telling it a paid ``richness='rich'`` retry
      is available for this hard page (that is precisely when Firecrawl earns its cost).
    - ``barrier: true`` when even a ``rich`` read is degraded/failed — free + paid both
      exhausted, so the source is genuinely walled (the cue to honestly caveat, not keep trying).
    """
    from ..depth.fetch_content import _fetch

    try:
        result = _fetch(url, allow_paid_fallback=rich)
    except Exception as exc:  # noqa: BLE001 — return a clean message, never crash the loop
        out = {"action": "read", "url": url, "error": str(exc)[:200]}
        if rich:
            out["barrier"] = True
        else:
            out["retry_hint"] = "free read failed on a hard page — retry richness='rich' (paid crawler)"
        return out
    # Only a GOOD extraction is a real deep read that grounds a claim. A thin/blocked bot-wall
    # must NOT falsely ground — snapshot (the grounding signal) only on good content.
    if result.get("content") and result.get("quality") == "good":
        snapshots.record(result.get("url", url), result["content"])
    out = {"action": "read", **result}
    if result.get("quality") != "good":
        if rich:
            out["barrier"] = True  # free + paid both degraded — a genuine wall
        else:
            out["retry_hint"] = (
                f"extraction was '{result.get('quality')}', not a full read — retry this url with "
                "richness='rich' for the paid crawler if this source matters"
            )
    return out


def _search_web(query: str, kind: str, max_results: int) -> dict[str, Any]:
    """Route to the right engine by intent: semantic -> Exa, else Tavily."""
    try:
        if kind == "semantic":
            from .exa import _build as build_engine
        else:
            from .tavily import _build as build_engine
        results = build_engine().invoke({"query": query})
    except Exception as exc:  # noqa: BLE001 — surface a clean error to the agent
        return {"action": "search", "kind": kind, "query": query, "error": str(exc)[:200]}
    # Meter the call's cost (these tiers are cheap, but real beyond free quota) so
    # the run's USD cap reflects total spend, not just the gated paid channels.
    cost.add(cost.estimate_call_cost(kind))
    return {"action": "search", "kind": kind, "query": query, "results": results}


def _build() -> Any:
    return as_structured_tool(
        _search,
        name="web_search",
        description=(
            "One research tool. Search the web (kind='keyword' or 'semantic'), read a page "
            "(read_url=...; richness='rich' allows the paid crawler on a hard page), or search "
            "LIVE X POSTS (source='x'). X is a distinct source class, not a fallback: reach for it "
            "when a story is unfolding, when you need the primary post rather than an outlet's "
            "summary of it, or to find credible on-the-ground dissent from the wire consensus. "
            "Web search and reads are free; 'rich' and 'x' draw on a small per-run budget."
        ),
    )


SPEC = ToolSpec(
    tool_id=WEB_SEARCH_TOOL_ID,
    name="web_search",
    description="Unified, cost-aware research surface: web search + page read + (X).",
    scope=GLOBAL_SCOPE,
    build=_build,
    channel="search",
)
