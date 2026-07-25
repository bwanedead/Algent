"""
The promotion router — the first concrete use of the generic engine (t1 -> t2).

It does nothing the engine doesn't already do; it just supplies the two
stage-specific things: the **brief** (the "rank every vector for the house reader" job)
and the **adapter** that renders t1 ``ResearchVector``s into generic candidates.

Cooldown is a list of recent published headlines in the agent payload — the model
flags same-story-family matches. No lexical post-filter. Alongside it rides a
coarser **recurring coverage** list (what our recent output keeps returning to).

The agent scores, but the score does not choose. Promotion is a **lottery over the
eligible** — see ``_ENV_MODE`` for why, and for how to switch back. The agent's real
authority here is the gate (cooldown), not the order.
"""

from __future__ import annotations

import os
import random
from dataclasses import replace

from algent_backend.agent_system.agents.discovery.portfolio import (
    ResearchPortfolio,
    ResearchVector,
)
from algent_backend.agent_system.foundation.models import ModelSpec
from algent_backend.agent_system.runs.context import AgentRunContext

from .contracts import RankedChoice, RouteCandidate, RouteRanking, RoutingBrief
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
        "the same story-family as a recent published headline (semantic judgment) OR matches "
        "an operator TOPIC FREEZE line (dev hard-block). Separately, WHAT WE KEEP CIRCLING "
        "breaks ties: between comparable vectors, prefer the one further from ground we "
        "have been working over and over."
    ),
    downstream=(
        "One vector is promoted into a t2 signal profile and becomes an article. Which one "
        "is NOT decided by your score: the promote order is drawn by lottery among the "
        "vectors you leave cooldown=false, because a fixed scoring criterion applied every "
        "day produces the same kind of winner every day. Your score is recorded for audit "
        "and for the human reading the queue; treat it as your honest read of importance, "
        "not as a vote. What your judgment DOES decide is eligibility: a cooldown=true "
        "vector cannot be drawn. Cooled vectors stay in the list for audit. The full "
        "ordered list is the on-deck queue."
    ),
    rank_all=True,
    top_k=80,
)

# Editorial judgment over a full portfolio — savvy tier, one structured call.
DEFAULT_MODEL = ModelSpec(provider="openai", model="gpt-5.4-mini", temperature=0.2)

# How the promote order is decided once the agent has judged cooldown.
#
#   "lottery" (default) — shuffle the eligible vectors. No score decides the order.
#   "rank"              — the agent's 0-100 composite, highest first.
#
# Lottery is the default because the composite score was manufacturing the rut it was
# meant to avoid. Its first five criteria — scale, magnitude, durability,
# irreversibility, urgency — are all monotonic in "how large is this conflict or macro
# event", so the same *kind* of story wins every single day, and novelty/curiosity sat
# as nudges inside a function that magnitude dominates. Live: the Iran-Israel-Red Sea
# cluster scored 96 and oil 85, while a solar generation record scored 66 and a
# scholarship-migration story 27. A criterion applied daily is a rut with extra steps.
#
# What survives is a **floor, not a ranking**: don't repeat ourselves (cooldown), don't
# run what an operator froze, and don't send research after something with nothing to
# research. Those are binary and defensible. Ordering the survivors by anything else is
# an editorial worldview, so it is left to chance instead.
#
# The cost is real and worth stating: on a day when something enormous happens, the
# lottery can lead with a small story while the big one waits its turn. Set
# ALGENT_PROMOTE_MODE=rank to get the old behaviour back.
_ENV_MODE = "ALGENT_PROMOTE_MODE"


def promote_mode() -> str:
    mode = os.environ.get(_ENV_MODE, "lottery").strip().lower()
    return mode if mode in ("lottery", "rank") else "lottery"


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
    recent, saturated = _recently_published()
    brief = replace(PROMOTION_BRIEF, recent=recent, saturated=saturated)

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
    # Operator hard-freeze (dev): force cooldown on matching vectors after agent rank.
    ranking, freeze_hits = apply_topic_freeze(ranking, by_id)
    mode = promote_mode()
    if mode == "lottery":
        ranking = apply_promotion_lottery(ranking, by_id, seed=portfolio.generated_at)

    try:
        cooled = [c.candidate_id for c in ranking.choices if c.cooldown]
        top = top_vector(ranking, by_id)
        context.emit("routing.cooldown_status", {
            "n_recent": len(recent),
            "recent_titles": [t[:80] for _, t in recent[:12]],
            "recurring_coverage": [f"{label}×{n}" for label, n in saturated[:8]],
            "promote_mode": mode,
            "mode": "agent_semantic+recurring_coverage+topic_freeze",
            "n_flagged": len(cooled),
            "cooled_ids": cooled,
            "topic_freeze_hits": freeze_hits,
            "promote_id": top.id if top else None,
            "promote_title": (top.title[:100] if top else None),
            "note_tail": (ranking.note or "")[-240:],
        })
    except Exception:  # noqa: BLE001
        pass
    return ranking, by_id


def apply_promotion_lottery(
    ranking: RouteRanking,
    by_id: dict[str, ResearchVector],
    *,
    seed: str = "",
) -> RouteRanking:
    """Shuffle the eligible vectors into a promote order. Scores are kept, not obeyed.

    Eligible = not cooled (recent story-family or operator freeze) and groundable. The
    order among them is chance. Cooled vectors keep their place at the end so the
    on-deck queue stays readable and the audit trail keeps every score.

    ``seed`` makes the draw reproducible for a given portfolio — the same portfolio
    always yields the same order, so an operator can work down the queue across runs
    (and a re-run with ``--from-run`` walks the same list) rather than getting a fresh
    shuffle each time. Cooldown is what stops repeats: once a piece is published its
    story-family is cooled, so the next draw cannot land on it again.
    """
    if not ranking.choices:
        return ranking

    eligible = [c for c in ranking.choices if not c.cooldown and _groundable(by_id.get(c.candidate_id))]
    held = [c for c in ranking.choices if c not in eligible]
    if not eligible:
        return ranking

    random.Random(seed or None).shuffle(eligible)
    ordered = [
        c.model_copy(update={"rank": i})
        for i, c in enumerate(eligible + held, start=1)
    ]
    note_bits = [ranking.note.strip()] if ranking.note.strip() else []
    note_bits.append(
        f"promote order drawn by lottery over {len(eligible)} eligible vectors "
        "(scores retained for audit, not used for ordering)"
    )
    return ranking.model_copy(update={"choices": ordered, "note": " | ".join(note_bits)})


def _groundable(vector: ResearchVector | None) -> bool:
    """The one non-negotiable floor: there has to be something to research."""
    if vector is None:
        return False
    return bool(vector.supporting_hits or vector.sources)


def apply_topic_freeze(
    ranking: RouteRanking,
    by_id: dict[str, ResearchVector],
) -> tuple[RouteRanking, list[str]]:
    """Force cooldown on vectors matching ``topic_freeze.md``. Returns (ranking, hit lines)."""
    try:
        from algent_backend.data_ingestion.newsroom.topic_freeze import (
            load_freeze_phrases,
            match_freeze,
        )
    except Exception:  # noqa: BLE001
        return ranking, []

    phrases = load_freeze_phrases()
    if not phrases or not ranking.choices:
        return ranking, []

    hits: list[str] = []
    updated: list[RankedChoice] = []
    for ch in ranking.choices:
        vec = by_id.get(ch.candidate_id)
        blob = (
            f"{vec.title} {vec.thesis} {vec.rationale}"
            if vec is not None
            else ch.candidate_id
        )
        phrase = match_freeze(blob, phrases)
        if phrase:
            hits.append(f"{ch.candidate_id}:{phrase}")
            updated.append(ch.model_copy(update={
                "cooldown": True,
                "cooldown_reason": f"topic freeze: {phrase}",
            }))
        else:
            updated.append(ch)

    if not hits:
        return ranking, []

    free = [c for c in updated if not c.cooldown]
    cooled = [c for c in updated if c.cooldown]
    ordered = [
        c.model_copy(update={"rank": i})
        for i, c in enumerate(free + cooled, start=1)
    ]
    note_bits = [ranking.note.strip()] if ranking.note.strip() else []
    note_bits.append(
        f"topic freeze forced cooldown on {len(hits)}: " + "; ".join(hits[:8])
    )
    return ranking.model_copy(update={"choices": ordered, "note": " | ".join(note_bits)}), hits


def _recently_published() -> tuple[tuple[tuple[str, str], ...], tuple[tuple[str, int], ...]]:
    """(headlines, recurring subjects) from recent output — the two cooldown payloads.

    Headlines drive the story-family cooldown; recurring subjects are the coarser rut
    tie-break. Best-effort: no site history is a valid state, not an error.
    """
    try:
        from algent_backend.publishing import site_git
        from algent_backend.publishing.history import recent_headlines, recurring_coverage

        root = site_git.repo_root()
        dirs = [site_git.live_site_dir(root), site_git.site_dir(root)]
        return tuple(recent_headlines(dirs)), tuple(recurring_coverage(dirs))
    except Exception:  # noqa: BLE001
        return (), ()


def top_vector(ranking: RouteRanking, by_id: dict[str, ResearchVector]) -> ResearchVector | None:
    """First non-cooldown ranked vector — the one to promote into a profile."""
    for choice in ranking.choices:
        if choice.cooldown:
            continue
        if choice.candidate_id in by_id:
            return by_id[choice.candidate_id]
    return None
