"""
The rake stage — chunked nano triage that prunes the t0 pool before synthesis.

``run_rake`` takes the t0 ``DiscoveryPool`` (as a dict), splits it into chunks, and
runs one cheap nano ReAct scout per chunk to keep-or-toss each item. It is:

- **fail-open**: only items a scout *explicitly* verdicts ``keep=false`` are dropped.
  Anything unverdicted (a chunk that errored, a cost-cap cutoff, an id the model
  forgot) passes through — a cheap pre-filter must never silently lose real news.
- **pre-vetted passthrough**: items already LLM-vetted upstream (X/grok, tagged
  ``signals.pre_vetted``) skip rake entirely and go straight to synthesis.
- **self-metered**: it opens its own free-channel policy scope and a nano-priced
  cost scope, so its spend is bounded and attributed to the nano tier, not synthesis.

Returns the pruned pool dict, a :class:`RakeSummary`, and the stage's estimated USD.
Best-effort: any failure leaves the original pool unchanged.
"""

from __future__ import annotations

from collections import Counter, defaultdict
from collections.abc import Callable
from typing import Any

from langchain_core.messages import HumanMessage

from algent_backend.agent_system.agents.loop import build_react_loop, stream_react_loop
from algent_backend.agent_system.foundation import cost
from algent_backend.agent_system.foundation.models import ModelSpec
from algent_backend.agent_system.runs.context import AgentRunContext
from algent_backend.agent_system.tools.sourcing.search import policy

from .contracts import RakeChunkResult, RakeSummary
from .messages import build_chunk_message
from .spec import (
    RAKE_CHANNELS,
    RAKE_CHUNK_SIZE,
    RAKE_COST_CAP_USD,
    RAKE_MODEL,
    RAKE_PAID_BUDGET,
    TOOL_IDS,
)
from .prompts import SYSTEM_PROMPT

ProgressFn = Callable[[str], None]


def run_rake(
    context: AgentRunContext,
    pool: dict[str, Any],
    *,
    config: Any = None,
    model_spec: ModelSpec = RAKE_MODEL,
    chunk_size: int = RAKE_CHUNK_SIZE,
    cost_cap_usd: float = RAKE_COST_CAP_USD,
    on_progress: ProgressFn | None = None,
) -> tuple[dict[str, Any], RakeSummary, float]:
    """Prune ``pool`` with a chunked nano scout. Returns (pruned_pool, summary, usd)."""
    say = on_progress or (lambda _m: None)
    items: list[dict[str, Any]] = list(pool.get("items", []))
    pre_vetted = [it for it in items if (it.get("signals") or {}).get("pre_vetted")]
    rakeable = [it for it in items if not (it.get("signals") or {}).get("pre_vetted")]

    if not rakeable:
        say(f"nothing to rake ({len(pre_vetted)} pre-vetted items pass straight through)")
        return pool, RakeSummary(pre_vetted=len(pre_vetted)), 0.0

    chunks = _chunks(rakeable, max(1, chunk_size))
    say(f"raking {len(rakeable)} items in {len(chunks)} chunk(s) (nano scout; {len(pre_vetted)} pre-vetted skip)…")

    model = context.model_resolver.resolve(model_spec).client
    tools = [context.tools[tool_id] for tool_id in TOOL_IDS]
    agent = build_react_loop(model, tools, system_prompt=SYSTEM_PROMPT, response_format=RakeChunkResult)
    # The scout free-reads sources to ground its keepers, so it needs room for several
    # tool calls per chunk — give it its own step budget rather than the run's turn cap.
    rake_config = {**(config or {}), "recursion_limit": max(int(chunk_size) * 4 + 8, 30)}

    by_id = {it.get("id"): it for it in rakeable}
    dropped: dict[str, str] = {}  # id -> reason, for items explicitly tossed
    enriched = 0
    with policy.scoped(RAKE_CHANNELS, RAKE_PAID_BUDGET), cost.scoped(cost_cap_usd, model_spec.model):
        for idx, chunk in enumerate(chunks, 1):
            chunk_ids = {it.get("id") for it in chunk}
            result = stream_react_loop(
                agent,
                {"messages": [HumanMessage(content=build_chunk_message(chunk))]},
                context=context,
                config=rake_config,
            )
            tossed_here = 0
            if isinstance(result, RakeChunkResult):
                for v in result.verdicts:
                    if v.id not in chunk_ids:
                        continue
                    if not v.keep:
                        dropped[v.id] = v.reason
                        tossed_here += 1
                    elif _apply_enrichment(by_id.get(v.id), v):
                        enriched += 1
            say(f"chunk {idx}/{len(chunks)}: kept {len(chunk) - tossed_here}/{len(chunk)}")
            if cost.over_cap():  # fail-open: leave the rest of the pool unraked
                say("rake cost cap reached — remaining items pass through unraked")
                break
        spent = cost.spent_usd()

    kept_rakeable = [it for it in rakeable if it.get("id") not in dropped]
    kept_items = kept_rakeable + pre_vetted
    summary = RakeSummary(
        considered=len(rakeable),
        kept=len(kept_rakeable),
        dropped=len(dropped),
        enriched=enriched,
        pre_vetted=len(pre_vetted),
        chunks=len(chunks),
        estimated_usd=round(spent, 6),
        dropped_examples=_dropped_examples(rakeable, dropped),
    )
    say(
        f"rake done: kept {summary.kept}/{summary.considered}, dropped {summary.dropped}, "
        f"grounded {summary.enriched} (+{summary.pre_vetted} pre-vetted)"
    )
    return _rebuild_pool(pool, kept_items), summary, spent


def _apply_enrichment(item: dict[str, Any] | None, verdict: Any) -> bool:
    """Ground a kept item with the scout's read: real headline -> label, synopsis ->
    signals. Returns True if anything was attached."""
    if item is None or not (verdict.headline or verdict.synopsis):
        return False
    signals = item.setdefault("signals", {})
    if verdict.headline:
        # Preserve the original deterministic label for traceability; lead with the real story.
        signals.setdefault("t0_label", item.get("label"))
        item["label"] = verdict.headline.strip()[:140]
    if verdict.synopsis:
        signals["synopsis"] = verdict.synopsis.strip()[:300]
    return True


def _chunks(items: list[dict[str, Any]], size: int) -> list[list[dict[str, Any]]]:
    return [items[i : i + size] for i in range(0, len(items), size)]


def _dropped_examples(rakeable: list[dict[str, Any]], dropped: dict[str, str], limit: int = 8) -> list[str]:
    by_id = {it.get("id"): it for it in rakeable}
    out = []
    for item_id, reason in list(dropped.items())[:limit]:
        label = (by_id.get(item_id, {}).get("label") or item_id)[:50]
        out.append(f"{label} — {reason[:80]}" if reason else label)
    return out


def _rebuild_pool(pool: dict[str, Any], items: list[dict[str, Any]]) -> dict[str, Any]:
    """A copy of the pool carrying only the kept items, with counts/facets recomputed."""
    facets: dict[str, list[str]] = defaultdict(list)
    for item in items:
        for pillar in item.get("pillars", []) or []:
            facets[pillar].append(item.get("id"))
    new = dict(pool)
    new["items"] = items
    new["item_count"] = len(items)
    new["by_channel"] = dict(Counter(it.get("channel") for it in items))
    new["by_pillar"] = {p: len(ids) for p, ids in facets.items()}
    new["facets"] = dict(facets)
    return new
