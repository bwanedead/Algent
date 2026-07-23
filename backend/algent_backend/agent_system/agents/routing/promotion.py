"""
The promotion router — the first concrete use of the generic engine (t1 -> t2).

It does nothing the engine doesn't already do; it just supplies the two
stage-specific things: the **brief** (the "rank every vector for the house reader" job)
and the **adapter** that renders t1 ``ResearchVector``s into generic candidates.

Cooldown is a list of recent published headlines in the agent payload — the model
flags same-story-family matches. No lexical post-filter.
"""

from __future__ import annotations

from dataclasses import replace

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
    role="the promotion editor ranking every research vector for what we should write next",
    candidate_kind="t1 signal vectors (theses worth pursuing, each fused from t0 hits)",
    selecting_for=(
        "FULL ORDERING of all vectors for the HOUSE READER: an intelligent, reasonably "
        "well-informed adult who follows the news but is NOT a specialist in any field. "
        "Score each vector 0-100 as a composite of: "
        "(a) SCALE — how many people are affected, and how directly. "
        "(b) MAGNITUDE — economic weight: dollars, jobs, prices people pay. "
        "(c) DURABILITY — structural change vs one-week blip. "
        "(d) IRREVERSIBILITY — one-way doors (deaths, treaties, elections, precedents). "
        "(e) URGENCY — real time-sensitivity; multiplies the others, does not replace them. "
        "(f) NOVELTY / under-coverage — what a general reader would *not* already get from "
        "every homepage. **Boost this.** "
        "(g) CURIOSITY / AWE / NEW HUMAN KNOWLEDGE — science breakthroughs, archaeology, "
        "physics, biology, math feats, genuine discoveries. **Weigh this harder.** "
        "GROUNDABILITY IS A GATE — demote unresearchable or pure trade/professional runbooks. "
        "When significance is comparable, prefer novel or wonder-inducing over mainstream rehash. "
        "Rank EVERY vector — do not drop to a shortlist. Flag cooldown=true when the vector is "
        "the same story-family as a recent published headline (semantic judgment)."
    ),
    downstream=(
        "The highest-ranked vector with cooldown=false is promoted into a t2 signal profile. "
        "Cooldown=true vectors stay in the ordered list for audit but will not promote. "
        "The full ordered list is the on-deck queue."
    ),
    rank_all=True,
    top_k=80,
)

# Editorial judgment over a full portfolio — savvy tier, one structured call.
DEFAULT_MODEL = ModelSpec(provider="openai", model="gpt-5.4-mini", temperature=0.2)


def rank_portfolio(
    context: AgentRunContext,
    portfolio: ResearchPortfolio,
    *,
    model_spec: ModelSpec = DEFAULT_MODEL,
    config: object = None,
) -> tuple[RouteRanking, dict[str, ResearchVector]]:
    """Rank a t1 portfolio for promotion. Returns (ranking, candidate_id -> vector).

    Candidate ids are the vectors' durable ids (positional fallback if a vector
    hasn't been assigned one); the returned map recovers the actual vectors.
    """
    recent = _recently_published()
    brief = replace(PROMOTION_BRIEF, recent=recent)

    candidates: list[RouteCandidate] = []
    by_id: dict[str, ResearchVector] = {}
    for i, vec in enumerate(portfolio.vectors):
        cid = vec.id or f"vec:{i:02d}"
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
    ranking = route(context, candidates, brief, model_spec=model_spec, config=config)

    try:
        cooled = [c.candidate_id for c in ranking.choices if c.cooldown]
        top = top_vector(ranking, by_id)
        context.emit("routing.cooldown_status", {
            "n_recent": len(recent),
            "recent_titles": [t[:80] for _, t in recent[:12]],
            "mode": "agent_semantic",
            "n_flagged": len(cooled),
            "cooled_ids": cooled,
            "promote_id": top.id if top else None,
            "promote_title": (top.title[:100] if top else None),
            "note_tail": (ranking.note or "")[-240:],
        })
    except Exception:  # noqa: BLE001
        pass
    return ranking, by_id


def _recently_published() -> tuple[tuple[str, str], ...]:
    """Recent published headlines — payload for agent cooldown. Best-effort."""
    try:
        from algent_backend.publishing import site_git
        from algent_backend.publishing.history import recent_headlines

        root = site_git.repo_root()
        return tuple(recent_headlines([site_git.live_site_dir(root), site_git.site_dir(root)]))
    except Exception:  # noqa: BLE001
        return ()


def top_vector(ranking: RouteRanking, by_id: dict[str, ResearchVector]) -> ResearchVector | None:
    """First non-cooldown ranked vector — the one to promote into a profile."""
    for choice in ranking.choices:
        if choice.cooldown:
            continue
        if choice.candidate_id in by_id:
            return by_id[choice.candidate_id]
    return None
