"""
The promotion router — the first concrete use of the generic engine (t1 -> t2).

It does nothing the engine doesn't already do; it just supplies the two
stage-specific things: the **brief** (the "pick the most profile-worthy vector" job)
and the **adapter** that renders t1 ``ResearchVector``s into generic candidates. This
is the pattern for every future router: a brief + an adapter, no new machinery.

Only this module knows about t1 types; the generic engine stays decoupled.
"""

from __future__ import annotations

from algent_backend.agent_system.agents.discovery.portfolio import (
    ResearchPortfolio,
    ResearchVector,
)
from algent_backend.agent_system.foundation.models import ModelSpec
from algent_backend.agent_system.runs.context import AgentRunContext

from .contracts import RouteCandidate, RouteRanking, RoutingBrief
from .engine import route

# The injected responsibility for the t1->t2 promotion decision.
PROMOTION_BRIEF = RoutingBrief(
    role="the promotion editor deciding which signal vector to research next",
    candidate_kind="t1 signal vectors (theses worth pursuing, each fused from t0 hits)",
    selecting_for=(
        "the single most worth-profiling vector right now — weigh importance, public "
        "interest, novelty/under-coverage, how compelling a production it could yield, "
        "and how well it can be grounded in real evidence"
    ),
    downstream=(
        "the #1 you rank is promoted into a t2 signal profile — a researched dossier "
        "with a claim + source ledger — which later renders into productions (article, "
        "post, chart, ...). Lower ranks are the on-deck queue"
    ),
    top_k=10,
)

# Editorial judgment over a couple dozen candidates — the savvy tier, one cheap call.
DEFAULT_MODEL = ModelSpec(provider="openai", model="gpt-5.4-mini", temperature=0.2)


def rank_portfolio(
    context: AgentRunContext,
    portfolio: ResearchPortfolio,
    *,
    model_spec: ModelSpec = DEFAULT_MODEL,
) -> tuple[RouteRanking, dict[str, ResearchVector]]:
    """Rank a t1 portfolio for promotion. Returns (ranking, candidate_id -> vector).

    Candidate ids are the vectors' durable ids (positional fallback if a vector
    hasn't been assigned one); the returned map recovers the actual vectors.
    """
    candidates: list[RouteCandidate] = []
    by_id: dict[str, ResearchVector] = {}
    for i, vec in enumerate(portfolio.vectors):
        cid = vec.id or f"vec:{i:02d}"  # durable id once synthesis assigns one
        by_id[cid] = vec
        candidates.append(RouteCandidate(
            id=cid,
            label=vec.title,
            summary=f"{vec.thesis} — {vec.rationale}",
            tags=list(vec.pillars),
            signals={
                "type": vec.vector_type,
                "effort": vec.research_effort,
                "supporting_hits": len(vec.supporting_hits),
                "sources": len(vec.sources),
            },
        ))
    ranking = route(context, candidates, PROMOTION_BRIEF, model_spec=model_spec)
    return ranking, by_id


def top_vector(ranking: RouteRanking, by_id: dict[str, ResearchVector]) -> ResearchVector | None:
    """The #1-ranked vector — the one to promote into a profile (programmatic pick)."""
    for choice in ranking.choices:
        if choice.candidate_id in by_id:
            return by_id[choice.candidate_id]
    return None
