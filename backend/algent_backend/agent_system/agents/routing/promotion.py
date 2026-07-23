"""
The promotion router — the first concrete use of the generic engine (t1 -> t2).

It does nothing the engine doesn't already do; it just supplies the two
stage-specific things: the **brief** (the "pick the most profile-worthy vector" job)
and the **adapter** that renders t1 ``ResearchVector``s into generic candidates. This
is the pattern for every future router: a brief + an adapter, no new machinery.

Only this module knows about t1 types; the generic engine stays decoupled.
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
from .cooldown import demote_cooled
from .engine import route

# The injected responsibility for the t1->t2 promotion decision.
PROMOTION_BRIEF = RoutingBrief(
    role="the promotion editor deciding which signal vector to research next",
    candidate_kind="t1 signal vectors (theses worth pursuing, each fused from t0 hits)",
    selecting_for=(
        "the single most worth-profiling vector right now, judged for the HOUSE READER: an "
        "intelligent, reasonably well-informed adult who follows the news but is NOT a specialist "
        "in any field. "
        "RANKING AXIS — reader SIGNIFICANCE *plus* CURIOSITY/AWE. We are not only a wire "
        "digest of the same war/macro head everyone covers. Score as a composite (say which "
        "carry the story): "
        "(a) SCALE — how many people are affected, and how directly. "
        "(b) MAGNITUDE — economic weight: dollars, jobs, prices people pay. "
        "(c) DURABILITY — structural change vs one-week blip. "
        "(d) IRREVERSIBILITY — one-way doors (deaths, treaties, elections, precedents). "
        "(e) URGENCY — real time-sensitivity; multiplies the others, does not replace them. "
        "(f) NOVELTY / under-coverage — what a general reader would *not* already get from "
        "every homepage. **Boost this.** Unique X-native or under-covered angles outrank "
        "yet another rehash of the same mega-beat when stakes are comparable. "
        "(g) CURIOSITY / AWE / NEW HUMAN KNOWLEDGE — science breakthroughs, archaeology, "
        "physics, biology, math feats, genuine discoveries, cool accomplishments that make "
        "a smart reader lean in (e.g. AI disproves a long-standing conjecture; first fossil; "
        "new telescope result). **Weigh this harder than before.** Enjoyable, high-signal "
        "knowledge stories are first-class, not 'soft' also-rans. "
        "GROUNDABILITY IS A GATE, NOT A SCORE — ineligible if unresearchable; no bonus for "
        "easy cites. Trade/professional runbooks demote. "
        "When significance is comparable, prefer the more novel or wonder-inducing vector "
        "over the most mainstream. Not all-out fringe — still real, grounded, transferable "
        "to a Western generalist — but turn the novelty/curiosity knobs UP. "
        "BEAT DIVERSITY: if ALREADY COVERED holds a story-family, do NOT rank that family #1 "
        "unless a true structural delta; prefer a genuinely different vector."
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
    config: object = None,
) -> tuple[RouteRanking, dict[str, ResearchVector]]:
    """Rank a t1 portfolio for promotion. Returns (ranking, candidate_id -> vector).

    Candidate ids are the vectors' durable ids (positional fallback if a vector
    hasn't been assigned one); the returned map recovers the actual vectors.
    """
    brief = PROMOTION_BRIEF
    if recent := _recently_published():
        brief = replace(brief, recent=recent)

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
    ranking = route(context, candidates, brief, model_spec=model_spec, config=config)
    # Soft instruction alone can re-promote the same beat under a reframe; mechanical floor
    # demotes same-family candidates below fresh ones so they cannot promote while hot.
    # Always run demote_cooled (even with empty recent) so the ranking note records status.
    before_top = ranking.choices[0].candidate_id if ranking.choices else ""
    ranking = demote_cooled(ranking, candidates, recent)
    after_top = ranking.choices[0].candidate_id if ranking.choices else ""
    try:
        context.emit("routing.cooldown_status", {
            "n_recent": len(recent),
            "recent_titles": [t[:80] for _, t in recent[:8]],
            "was_top": before_top,
            "now_top": after_top,
            "demoted": bool(before_top and after_top and before_top != after_top),
            "note_tail": (ranking.note or "")[-280:],
        })
        if before_top and after_top and before_top != after_top:
            context.emit("routing.cooldown_demote", {
                "was_top": before_top, "now_top": after_top, "note": ranking.note[-240:],
            })
    except Exception:  # noqa: BLE001 — telemetry must never break the pick
        pass
    return ranking, by_id


def _recently_published() -> tuple[tuple[str, str], ...]:
    """Recent published headlines — the cooldown reference. Best-effort: routing must never fail
    because the site is unreadable (a fresh clone has no published articles at all)."""
    try:
        from algent_backend.publishing import site_git
        from algent_backend.publishing.history import recent_headlines

        root = site_git.repo_root()
        # The live worktree is what is actually on the site; the working tree catches staged pieces
        # when the publish kill switch is off.
        return tuple(recent_headlines([site_git.live_site_dir(root), site_git.site_dir(root)]))
    except Exception:  # noqa: BLE001
        return ()


def top_vector(ranking: RouteRanking, by_id: dict[str, ResearchVector]) -> ResearchVector | None:
    """The #1-ranked vector — the one to promote into a profile (programmatic pick)."""
    for choice in ranking.choices:
        if choice.candidate_id in by_id:
            return by_id[choice.candidate_id]
    return None
