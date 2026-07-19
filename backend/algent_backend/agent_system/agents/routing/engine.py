"""
The routing engine — ``route``: rank candidates against a brief, tool-free.

The generic primitive every router in the system stands on. It's a single
structured-output model call (pure judgment — no tools, no loop), so it is:
- **stateless** — no instance state, safe to clone and run many in parallel/async;
- **reusable** — identical at every level; only the injected ``RoutingBrief`` differs;
- **decoupled** — it knows only generic candidates, never a stage-specific type.

LangChain lives here (the structured call); contracts/prompts stay rail-free.
"""

from __future__ import annotations

from langchain_core.messages import HumanMessage, SystemMessage

from algent_backend.agent_system.foundation.models import ModelSpec
from algent_backend.agent_system.runs.context import AgentRunContext

from .contracts import RouteCandidate, RouteRanking, RoutingBrief
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
            HumanMessage(content=build_router_message(candidates, brief.top_k, brief.recent)),
        ],
        config=config,
    )

    ranking = raw if isinstance(raw, RouteRanking) else _coerce(raw)
    # Trust only choices that name a real candidate; order best-first by rank.
    valid_ids = {c.id for c in candidates}
    choices = sorted(
        (ch for ch in ranking.choices if ch.candidate_id in valid_ids),
        key=lambda ch: ch.rank,
    )
    ranking = ranking.model_copy(update={"choices": choices})
    _emit(context, ranking, len(candidates))
    return ranking


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
        context.emit(ROUTING_DECISION, {
            "considered": considered,
            "ranked": len(ranking.choices),
            "top": [
                f"#{ch.rank} {ch.candidate_id} ({ch.score}) {ch.rationale[:80]}"
                for ch in ranking.choices[:5]
            ],
        })
    except Exception:
        pass
