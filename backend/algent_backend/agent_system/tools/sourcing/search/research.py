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
  prefers Tavily, falls through to Brave then Exa on hard provider failure;
  semantic prefers Exa, falls through to keyword engines.
- **scholarly resolve** — ``web_search(doi=...)`` or ``kind="scholar"`` — free
  Crossref/OpenAlex lookup for papers (no paid budget).
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
from . import circuit, policy

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
    """Authorize + settle one paid call (count budget AND dollar reserve). None = OK."""
    if cost.is_slim() or cost.is_hard_stop():
        cost.record_skip(channel, cost.mode())
        return {
            "error": f"channel '{channel}' skipped ({cost.mode()})",
            "budget_mode": cost.mode(),
        }
    est = cost.estimate_call_cost(channel)
    if not policy.try_spend_paid():
        return _budget_exhausted(channel)
    res = cost.try_reserve(est, op=channel)
    if res is None:
        return _cost_capped(channel)
    cost.settle(res, est)
    return None


def _can_afford_paid(channel: str) -> dict[str, Any] | None:
    """Check paid affordability without consuming budget. None = OK."""
    if cost.is_slim() or cost.is_hard_stop():
        cost.record_skip(channel, cost.mode())
        return {
            "error": f"channel '{channel}' skipped ({cost.mode()})",
            "budget_mode": cost.mode(),
        }
    est = cost.estimate_call_cost(channel)
    if cost.would_exceed(est):
        return _cost_capped(channel)
    if policy.remaining_paid_budget() <= 0:
        return _budget_exhausted(channel)
    return None


def _search(
    query: str = "",
    kind: str = "keyword",
    read_url: str = "",
    richness: str = "standard",
    source: str = "web",
    max_results: int = 5,
    doi: str = "",
) -> dict[str, Any]:
    """Investigate the web through one cost-aware surface. See the module docstring."""
    max_results = max(1, min(max_results, _MAX_RESULTS_CAP))
    if read_url:
        return _search_read(read_url, richness=richness)
    if doi or kind == "scholar":
        return _search_scholar(query=query, doi=doi)
    if source == "x":
        return _search_x(query, max_results)
    channel = policy.SEMANTIC if kind == "semantic" else policy.KEYWORD
    if not policy.is_allowed(channel):
        return _denied(channel)
    return _search_web(query, kind, max_results)


def _search_read(read_url: str, *, richness: str) -> dict[str, Any]:
    rich = richness == "rich"
    if not policy.is_allowed(policy.READ):
        return _denied(policy.READ)
    if rich:
        if not policy.is_allowed(policy.RICH):
            return _denied(policy.RICH)
        # Affordability check only — charge when Firecrawl is actually used.
        refusal = _can_afford_paid(policy.RICH)
        if refusal is not None:
            return refusal
    return _read(read_url, rich=rich)


def _search_scholar(*, query: str, doi: str) -> dict[str, Any]:
    if not policy.is_allowed(policy.KEYWORD) and not policy.is_allowed(policy.SEMANTIC):
        return _denied(policy.KEYWORD)
    from . import scholarly
    return scholarly.resolve(query=query, doi=doi)


def _search_x(query: str, max_results: int) -> dict[str, Any]:
    if not policy.is_allowed(policy.X):
        return _denied(policy.X)
    if cost.is_slim() or cost.is_hard_stop():
        cost.record_skip(policy.X, cost.mode())
        return {
            "error": f"channel 'x' skipped ({cost.mode()})",
            "budget_mode": cost.mode(),
        }
    # Reserve maximum for requested post count; settle actual returned posts.
    ceiling = cost.estimate_x_posts(max_results)
    if ceiling <= 0:
        ceiling = cost.estimate_call_cost(policy.X)
    if not policy.try_spend_paid():
        return _budget_exhausted(policy.X)
    res = cost.try_reserve(ceiling, op=policy.X)
    if res is None:
        return _cost_capped(policy.X)
    from .x_search import x_recent_search
    try:
        payload = x_recent_search(query, max_results)
    except Exception:
        cost.release(res)
        raise
    results = payload.get("results") or []
    actual = cost.estimate_x_posts(len(results) if isinstance(results, list) else 0)
    cost.settle(res, actual)
    return {
        "action": "search", "kind": "x",
        "estimated_usd": round(actual, 6),
        "posts": len(results) if isinstance(results, list) else 0,
        **payload,
    }


def _read(url: str, *, rich: bool) -> dict[str, Any]:
    """Read a page via the free-first fetch ladder (paid only when ``rich``).

    Two honest signals accompany a read so the agent (and doctrine) can act:
    - ``retry_hint`` on a *degraded free* read — telling it a paid ``richness='rich'`` retry
      is available for this hard page (that is precisely when Firecrawl earns its cost).
    - ``barrier: true`` when even a ``rich`` read is degraded/failed — free + paid both
      exhausted, so the source is genuinely walled (the cue to honestly caveat, not keep trying).
    """
    from ..depth.fetch_content import _fetch

    paid_res = None
    allow_paid = False
    rich_est = cost.estimate_call_cost(policy.RICH)
    if rich:
        # Rich is never essential finish-path spend — refuse under slim even inside essential_scope.
        paid_res = cost.try_reserve(rich_est, op=policy.RICH, essential=False)
        allow_paid = paid_res is not None

    try:
        result = _fetch(url, allow_paid_fallback=allow_paid)
    except Exception as exc:  # noqa: BLE001 — return a clean message, never crash the loop
        cost.release(paid_res)
        out = {"action": "read", "url": url, "error": str(exc)[:200]}
        if rich:
            out["barrier"] = True
        else:
            out["retry_hint"] = (
                "free read failed on a hard page — retry richness='rich' (paid crawler)"
            )
        return out
    # Charge rich budget only when Firecrawl actually rescued the page.
    if allow_paid and result.get("via") == "firecrawl":
        if policy.try_spend_paid():
            cost.settle(paid_res, rich_est)
        else:
            cost.release(paid_res)
            result = {**result, "budget_note": "rich budget unavailable"}
    else:
        cost.release(paid_res)
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
    """Route by intent with automatic fallthrough on hard provider failure.

    Primary: keyword→Tavily, semantic→Exa. On circuit-open or hard error, try Brave
    (independent index) then the other intent engine. Empty results alone do not trip
    the breaker — only quota/auth-class failures do. Provider-returned error payloads
    (e.g. Tavily ``{"error": ValueError("Error 432 quota exceeded")}``) count as hard
    failures too — Amazon 0041 returned that shape without raising.

    Every provider contact is authorized before contact and settled after.
    Slim/hard mode refuses fallback providers (optional expenditure).
    """
    chain = _provider_chain(kind)
    errors: list[str] = []
    meter_kind = kind if kind in ("keyword", "semantic") else "keyword"
    unit = cost.estimate_call_cost(meter_kind)
    for i, provider in enumerate(chain):
        if i > 0 and (cost.is_slim() or cost.is_hard_stop()):
            cost.record_skip("search_fallback", cost.mode())
            errors.append(f"{provider}: skipped ({cost.mode()} — no fallback search)")
            break
        if circuit.is_open(provider):
            errors.append(f"{provider}: circuit open")
            continue
        res = cost.try_reserve(unit, op=meter_kind)
        if res is None:
            errors.append(f"{provider}: cost refused ({cost.mode()})")
            break
        try:
            results = _invoke_provider(provider, query, max_results)
        except Exception as exc:  # noqa: BLE001
            cost.settle(res, unit)
            circuit.record_failure(provider, exc)
            errors.append(f"{provider}: {str(exc)[:120]}")
            continue
        cost.settle(res, unit)
        payload_err = _provider_error_payload(results)
        if payload_err is not None:
            circuit.record_failure(provider, payload_err)
            errors.append(f"{provider}: {payload_err[:120]}")
            continue
        circuit.record_success(provider)
        out: dict[str, Any] = {
            "action": "search", "kind": kind, "query": query,
            "provider": provider, "results": results,
            # WHICH engine answered decides how the next query should be phrased, and the
            # answer changes mid-run without warning: a quota or an outage silently moves
            # keyword search from a literal-match index onto a neural one, where the same
            # keyword-soup query performs worst. Naming the provider was not enough — the
            # agent could see it and had no idea what it implied.
            "provider_style": _PROVIDER_STYLE[provider],
        }
        if provider != chain[0]:
            out["fallback_from"] = chain[0]
            out["provider_note"] = (
                f"{chain[0]} was unavailable, so this came from {provider}. "
                f"If the results look off, RE-ASK in {provider}'s style rather than "
                f"repeating the same query."
            )
        return out
    return {
        "action": "search", "kind": kind, "query": query,
        "error": "; ".join(errors)[:300] or "all search providers failed",
        "providers_tried": chain,
    }


def _provider_error_payload(results: Any) -> str | None:
    """Extract a hard-failure message from a non-raising provider response, if any."""
    if isinstance(results, dict) and results.get("error") is not None:
        return str(results["error"])
    if isinstance(results, list) and len(results) == 1 and isinstance(results[0], dict):
        err = results[0].get("error")
        if err is not None:
            return str(err)
    return None


#: How to ask each engine, in the agent's own terms. These are retrieval styles, not vendor
#: trivia: the same question phrased for the wrong engine comes back thin, and the agent then
#: concludes the material does not exist rather than that it asked badly.
_PROVIDER_STYLE = {
    "tavily": (
        "literal-match, news-weighted: use the actual words a page would contain — names, "
        "places, quoted phrases. Short and concrete beats descriptive."
    ),
    "brave": (
        "literal keyword index: exact strings and distinctive terms. Best for a specific name, "
        "phrase or number; it will not infer what you meant."
    ),
    "muse": (
        "the model's OWN web search, used because the dedicated engines were unavailable. Ask "
        "in plain language, as you would ask a person to look something up. It chose its own "
        "queries, so results reflect its reading of your request — if they miss, restate what "
        "you actually need rather than reworking keywords."
    ),
    "exa": (
        "neural/semantic: DESCRIBE the page you want in a natural phrase — 'a study measuring X "
        "in Y' — rather than stacking keywords. Keyword soup is its weakest input, and an exact "
        "phrase lookup is better served by re-asking as a description of the source."
    ),
}


def _provider_chain(kind: str) -> list[str]:
    # `muse` is last on both: it is a genuine substitute at the snippet tier, but the model picks
    # its own queries and shows us what it chose to cite, where a keyword API answers the query we
    # wrote and returns everything. That is the right trade only once the alternatives are gone —
    # which, with tavily near its monthly cap and brave unconfigured, is a case we now reach.
    if kind == "semantic":
        return ["exa", "brave", "tavily", "muse"]
    return ["tavily", "brave", "exa", "muse"]


def _invoke_provider(provider: str, query: str, max_results: int) -> list[Any]:
    if provider == "tavily":
        from .tavily import _build as build_engine
        return build_engine().invoke({"query": query})
    if provider == "exa":
        from .exa import _build as build_engine
        return build_engine().invoke({"query": query})
    if provider == "brave":
        from .brave import _search as brave_search
        return brave_search(query, max_results=max_results)
    if provider == "muse":
        from .muse_search import search as muse_search
        return muse_search(query, max_results=max_results)
    raise RuntimeError(f"unknown search provider: {provider}")


def _build() -> Any:
    return as_structured_tool(
        _search,
        name="web_search",
        description=(
            "One research tool. Search the web (kind='keyword' or 'semantic'), resolve a paper "
            "(doi=... or kind='scholar'), read a page (read_url=...; richness='rich' allows the "
            "paid crawler on a hard page), or search LIVE X POSTS (source='x'). X is a distinct "
            "source class, not a fallback: reach for it when a story is unfolding, when you need "
            "the primary post rather than an outlet's summary of it, or to find credible "
            "on-the-ground dissent from the wire consensus. Web search and reads are free; "
            "'rich' and 'x' draw on a small per-run budget. Keyword search auto-falls through "
            "providers on quota failure — so every result names the `provider` that answered "
            "and a `provider_style` saying how that engine wants to be asked. Read it: a "
            "literal-match engine and a semantic one reward opposite phrasing, and which one "
            "you get can change mid-run. Thin results are often the wrong phrasing for the "
            "engine that happened to answer, not an absent source — re-ask in its style before "
            "concluding the material does not exist."
        ),
    )


SPEC = ToolSpec(
    tool_id=WEB_SEARCH_TOOL_ID,
    name="web_search",
    description="Unified, cost-aware research surface: web search + page read + scholar + (X).",
    scope=GLOBAL_SCOPE,
    build=_build,
    channel="search",
)
