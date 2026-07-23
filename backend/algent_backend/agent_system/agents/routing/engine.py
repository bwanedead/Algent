"""
The routing engine — ``route``: rank candidates against a brief, tool-free.

The generic primitive every router in the system stands on. It's a single
structured-output model call (pure judgment — no tools, no loop), so it is:
- **stateless** — no instance state, safe to clone and run many in parallel/async;
- **reusable** — identical at every level; only the injected ``RoutingBrief`` differs;
- **decoupled** — it knows only generic candidates, never a stage-specific type.

Cooldown is agent judgment (flags on each choice), not a post-hoc lexical matcher.
"""

from __future__ import annotations

from langchain_core.messages import HumanMessage, SystemMessage

from algent_backend.agent_system.foundation.models import ModelSpec
from algent_backend.agent_system.runs.context import AgentRunContext

from .contracts import RankedChoice, RouteCandidate, RouteRanking, RoutingBrief
from .prompts import build_router_message, build_router_system_prompt

ROUTING_DECISION = "routing.decision"  # event type for the run timeline


def route(
    context: AgentRunContext,
    candidates: list[RouteCandidate],
    brief: RoutingBrief,
    *,
    model_spec: ModelSpec,
    config: object = None,
) -> RouteRanking:
    """Rank ``candidates`` against ``brief`` and return the ranking (best-first).

    ``config`` is the run's RunnableConfig (if any) — threaded to the model call so
    its token usage is captured by the run's usage handler.
    """
    if not candidates:
        return RouteRanking(note="no candidates to route")

    model = context.model_resolver.resolve(model_spec).client
    structured = model.with_structured_output(RouteRanking)
    raw = structured.invoke(
        [
            SystemMessage(content=build_router_system_prompt(brief)),
            HumanMessage(content=build_router_message(candidates, brief)),
        ],
        config=config,
    )

    ranking = raw if isinstance(raw, RouteRanking) else _coerce(raw)
    ranking = _normalize_ranking(ranking, candidates, brief)
    _emit(context, ranking, len(candidates))
    return ranking


def _normalize_ranking(
    ranking: RouteRanking,
    candidates: list[RouteCandidate],
    brief: RoutingBrief,
) -> RouteRanking:
    """Keep valid ids, fill any missing candidates, re-stamp ranks 1..n.

    Order: agent order for cooldown=false first (promote-ready), then cooldown=true
    (audit-only). Within each band, preserve the model's relative order.
    """
    valid_ids = {c.id for c in candidates}
    by_id = {c.id: c for c in candidates}
    seen: set[str] = set()
    kept: list[RankedChoice] = []
    for ch in sorted(ranking.choices, key=lambda c: c.rank):
        if ch.candidate_id not in valid_ids or ch.candidate_id in seen:
            continue
        seen.add(ch.candidate_id)
        kept.append(ch)

    # Full-list mode: append anything the model skipped at the bottom (not cooled).
    if brief.rank_all:
        for c in candidates:
            if c.id in seen:
                continue
            kept.append(RankedChoice(
                candidate_id=c.id,
                rank=999,
                score=0.0,
                rationale="(model omitted — backfilled)",
                cooldown=False,
            ))

    free = [c for c in kept if not c.cooldown]
    cooled = [c for c in kept if c.cooldown]
    ordered = free + cooled
    new_choices = [
        ch.model_copy(update={"rank": i})
        for i, ch in enumerate(ordered, start=1)
    ]
    n_cool = len(cooled)
    note_bits = [ranking.note.strip()] if ranking.note.strip() else []
    if brief.recent:
        note_bits.append(
            f"agent cooldown: {n_cool}/{len(new_choices)} flagged "
            f"(n_recent_headlines={len(brief.recent)})"
        )
    else:
        note_bits.append("agent cooldown: no recent headlines in payload")
    return ranking.model_copy(update={
        "choices": new_choices,
        "note": " | ".join(note_bits),
    })


def _coerce(raw: object) -> RouteRanking:
    if isinstance(raw, dict):
        try:
            return RouteRanking(**raw)
        except (TypeError, ValueError):
            pass
    return RouteRanking(note="router returned no structured ranking")


def _emit(context: AgentRunContext, ranking: RouteRanking, considered: int) -> None:
    """Best-effort timeline event; a trace hiccup must never break a decision."""
    try:
        cooled = [c.candidate_id for c in ranking.choices if c.cooldown]
        free = [c for c in ranking.choices if not c.cooldown]
        context.emit(ROUTING_DECISION, {
            "considered": considered,
            "ranked": len(ranking.choices),
            "cooldown_flagged": len(cooled),
            "cooled_ids": cooled[:12],
            "top_eligible": (
                f"#{free[0].rank} {free[0].candidate_id} ({free[0].score}) "
                f"{(free[0].rationale or '')[:80]}"
                if free else "none"
            ),
            "top": [
                f"#{ch.rank} {ch.candidate_id} ({ch.score})"
                f"{' [cooldown]' if ch.cooldown else ''} {(ch.rationale or '')[:60]}"
                for ch in ranking.choices[:8]
            ],
        })
    except Exception:
        pass
