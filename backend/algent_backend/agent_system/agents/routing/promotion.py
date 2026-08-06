"""
The promotion router — the first concrete use of the generic engine (t1 -> t2).

It does nothing the engine doesn't already do; it just supplies the two
stage-specific things: the **brief** (the "rank every vector for the house reader" job)
and the **adapter** that renders t1 ``ResearchVector``s into generic candidates.

Cooldown is a list of recent published headlines in the agent payload — the model
flags same-story-family matches. No lexical post-filter. Alongside it rides a
coarser **recurring coverage** list (what our recent output keeps returning to).

The agent scores, but the score does not decide alone. Promotion is a **rut-discounted
weighted draw** over the eligible — importance tilts the odds, our own repetition
discounts them, chance settles the rest, and a genuinely enormous new story still leads
outright. See ``_ENV_MODE``. The agent's absolute authority is the gate (cooldown).
"""

from __future__ import annotations

import os
import random
from dataclasses import replace

from algent_backend.agent_system.agents.discovery.portfolio import (
    ResearchPortfolio,
    ResearchVector,
)
from algent_backend.agent_system.foundation.models import ModelSpec, house_spec
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
        "is NOT simply your top score. The promote order is a weighted random draw over "
        "the vectors you leave cooldown=false: your score sets the odds, and those odds "
        "are then discounted for how much a vector overlaps what our own recent output "
        "keeps circling — because a fixed criterion applied every day produces the same "
        "kind of winner every day. A very high score with no such overlap does lead "
        "outright. So score honestly on importance and it will count, but do not try to "
        "engineer the outcome; the anti-repetition correction happens after you. What "
        "your judgment alone decides is eligibility: a cooldown=true vector cannot be "
        "drawn at all. Cooled vectors stay in the list for audit. The full ordered list "
        "is the on-deck queue."
    ),
    rank_all=True,
    top_k=80,
)

# Editorial judgment over a full portfolio — medium effort when called without a spec.
DEFAULT_MODEL = house_spec(reasoning_effort="medium", temperature=0.2)

# How the promote order is decided once the agent has judged cooldown.
#
#   "draw" (default) — weighted random draw: importance tilts the odds, our own rut
#                      discounts them, chance settles the rest.
#   "rank"           — the agent's 0-100 composite, highest first (the original).
#
# Why not straight ranking. The composite manufactures the rut it exists to prevent:
# scale, magnitude, durability, irreversibility and urgency are all monotonic in "how
# large is this conflict or macro event", so the same *kind* of story wins every day and
# novelty sits as a nudge inside a function magnitude dominates. Live: Iran-Israel-Red
# Sea 96, oil 85, a record solar month 66, scholarship migration 27.
#
# Why not a flat lottery either. It answers stagnation by throwing away the one thing
# the score is actually good at — telling us when something genuinely enormous has
# happened. A flat draw leads with Turkey's solar record on the day a war starts.
#
# So: **weight the draw, and discount the rut.** A vector's odds are its importance
# score decayed by how much it overlaps what our own recent output keeps circling
# (``publishing.history.recurring_coverage``, read off published frontmatter). A big
# genuinely-new story keeps its full weight and usually leads. The eighth Hormuz piece
# has its weight cut per matching label, so it stops crowding the queue without ever
# being banned — and the discount *decays on its own* as we stop covering it, because
# the recurrence window is only ten days. Nothing is quota'd and no category is
# privileged; the penalty is descriptive of us, not prescriptive about the world.
#
# BREAK GLASS: a vector scoring at/above ``_ENV_BREAK_GLASS`` with zero rut overlap
# leads outright. That is the "something enormous and genuinely new happened" path, and
# it is rare by construction — it needs both a near-top score and no recurrence.
# Deliberate redo: re-run a story we have already published, to replace it.
#
# Cooldown exists to stop the newsroom covering the same thing night after night, and it
# does that by reading our own published headlines — which means it also blocks the one
# case where re-running is exactly right: a piece that shipped short of standard (a bug ate
# its figures, a source was wrong) and needs replacing rather than following up. Without an
# escape hatch the only way through is deleting the published article first, which is worse
# in every respect: it loses the corrections trail.
#
# Operator-only, per-run, and loud — the override is recorded in the emitted cooldown status
# so a redo can never be mistaken for the ring having lapsed.
_ENV_REDO = "ALGENT_PROMOTE_REDO"
_ENV_MODE = "ALGENT_PROMOTE_MODE"


def redo_enabled() -> bool:
    return os.environ.get(_ENV_REDO, "0").strip().lower() in ("1", "true", "yes", "on")


def clear_cooldown_for_redo(ranking: RouteRanking) -> RouteRanking:
    """Drop cooldown flags so an already-published story can be re-run and replaced."""
    if not ranking.choices:
        return ranking
    cooled = [c.candidate_id for c in ranking.choices if c.cooldown]
    if not cooled:
        return ranking
    freed = [
        c.model_copy(update={"cooldown": False,
                             "cooldown_reason": f"cleared by operator redo ({c.cooldown_reason})"})
        for c in ranking.choices
    ]
    note = (ranking.note + " | " if ranking.note.strip() else "") + (
        f"OPERATOR REDO: cooldown cleared on {len(cooled)} vector(s) — this run is expected to "
        "replace an already-published piece"
    )
    return ranking.model_copy(update={"choices": freed, "note": note})
_ENV_DECAY = "ALGENT_PROMOTE_RUT_DECAY"          # weight multiplier per matching label
_ENV_BREAK_GLASS = "ALGENT_PROMOTE_BREAK_GLASS"  # score at which magnitude just wins
_DECAY = 0.45
_BREAK_GLASS = 90.0


def promote_mode() -> str:
    mode = os.environ.get(_ENV_MODE, "draw").strip().lower()
    return mode if mode in ("draw", "rank") else "draw"


def _float_env(name: str, default: float, *, lo: float, hi: float) -> float:
    try:
        return max(lo, min(hi, float(os.environ.get(name, str(default)))))
    except ValueError:
        return default


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
    redo = redo_enabled()
    if redo:
        ranking = clear_cooldown_for_redo(ranking)
    mode = promote_mode()
    if mode == "draw":
        ranking = apply_promotion_draw(
            ranking, by_id, recurring=saturated, seed=portfolio.generated_at,
        )

    try:
        cooled = [c.candidate_id for c in ranking.choices if c.cooldown]
        top = top_vector(ranking, by_id)
        context.emit("routing.cooldown_status", {
            "n_recent": len(recent),
            "recent_titles": [t[:80] for _, t in recent[:12]],
            "recurring_coverage": [f"{label}×{n}" for label, n in saturated[:8]],
            "promote_mode": mode,
            "operator_redo": redo,
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


def apply_promotion_draw(
    ranking: RouteRanking,
    by_id: dict[str, ResearchVector],
    *,
    recurring: tuple[tuple[str, int], ...] = (),
    seed: str = "",
) -> RouteRanking:
    """Order the eligible vectors by a rut-discounted weighted draw. See ``_ENV_MODE``.

    Eligible = not cooled (recent story-family or operator freeze) and groundable.
    Weight = importance score × decay per recurring-coverage label the vector matches.
    A near-top score with no recurrence skips the draw entirely (break glass).

    ``seed`` makes the draw reproducible for a given portfolio, so an operator can work
    down the queue across runs instead of getting a fresh order each time. Cooldown is
    what stops repeats: once a piece is published, its story-family is cooled.
    """
    if not ranking.choices:
        return ranking

    eligible = [
        c for c in ranking.choices
        if not c.cooldown and _groundable(by_id.get(c.candidate_id))
    ]
    held = [c for c in ranking.choices if c not in eligible]
    if not eligible:
        return ranking

    decay = _float_env(_ENV_DECAY, _DECAY, lo=0.05, hi=1.0)
    break_glass = _float_env(_ENV_BREAK_GLASS, _BREAK_GLASS, lo=0.0, hi=1000.0)
    labels = _rut_labels(recurring)

    weights: dict[str, float] = {}
    ruts: dict[str, int] = {}
    forced: list[RankedChoice] = []
    drawable: list[RankedChoice] = []
    for choice in eligible:
        rut = _rut_overlap(by_id.get(choice.candidate_id), labels)
        ruts[choice.candidate_id] = rut
        weights[choice.candidate_id] = max(float(choice.score), 1.0) * (decay ** rut)
        if choice.score >= break_glass and rut == 0:
            forced.append(choice)
        else:
            drawable.append(choice)

    forced.sort(key=lambda c: -c.score)
    drawn = _weighted_order(drawable, weights, random.Random(seed or None))
    ordered = [
        c.model_copy(update={"rank": i})
        for i, c in enumerate(forced + drawn + held, start=1)
    ]

    note_bits = [ranking.note.strip()] if ranking.note.strip() else []
    discounted = sum(1 for n in ruts.values() if n)
    note_bits.append(
        f"promote order: weighted draw over {len(eligible)} eligible "
        f"(decay {decay} per rut label; {discounted} discounted for recurrence"
        + (f"; {len(forced)} led on break-glass score >= {break_glass:.0f}" if forced else "")
        + ")"
    )
    return ranking.model_copy(update={"choices": ordered, "note": " | ".join(note_bits)})


def _weighted_order(
    choices: list[RankedChoice], weights: dict[str, float], rng: random.Random
) -> list[RankedChoice]:
    """Draw without replacement, odds proportional to weight."""
    pool = list(choices)
    order: list[RankedChoice] = []
    while pool:
        total = sum(max(weights.get(c.candidate_id, 1.0), 0.0) for c in pool)
        if total <= 0:
            rng.shuffle(pool)
            return order + pool
        cut = rng.uniform(0.0, total)
        running = 0.0
        for index, choice in enumerate(pool):
            running += max(weights.get(choice.candidate_id, 1.0), 0.0)
            if running >= cut:
                order.append(pool.pop(index))
                break
        else:
            order.append(pool.pop())
    return order


def _rut_labels(recurring: tuple[tuple[str, int], ...]) -> list[str]:
    """The bare labels of what our recent output keeps circling ("place:Iran" -> "iran")."""
    out: list[str] = []
    for label, _count in recurring:
        bare = label.split(":", 1)[-1].strip().casefold()
        if len(bare) > 2:
            out.append(bare)
    return out


def _rut_overlap(vector: ResearchVector | None, labels: list[str]) -> int:
    """How many recurring labels this vector touches — the discount exponent."""
    if vector is None or not labels:
        return 0
    blob = " ".join([
        vector.title, vector.thesis, vector.rationale,
        " ".join(vector.pillars), " ".join(vector.scope),
    ]).casefold()
    return sum(1 for label in labels if label in blob)


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
