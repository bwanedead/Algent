"""
Ranking — score candidates and select a shortlist that resists the headline rut.

Two steps:

- **score** each candidate by blending the signals that matter for discovery:
  momentum (movement + breadth), a light significance floor, **novelty** (new to
  our memory — our asset vs wire sameness), **curiosity** (science / knowledge
  / discovery-shaped themes), **specificity** (event/story grain over mega-tags),
  and a **standing-topic penalty** (chronic baselines without novelty).
- **select** the shortlist with a *protected quota* for rising / novel /
  non-English / science-curiosity / event-shaped margins so loud war-macro
  cannot crowd them out.

Volume alone is the rut. Novelty, curiosity, and grain are boosted; standing
breadth is punished.
"""

from __future__ import annotations

from dataclasses import dataclass
from math import log1p

from .candidates import CandidateStats
from .memory import RollingMemory
from .stories import is_broad_theme

# Velocity smoothing: baselines this small or smaller can't manufacture huge
# acceleration from noise. ``(count - base) / (base + SMOOTHING)``.
SMOOTHING = 2.0
RISING_THRESHOLD = 0.5  # velocity at/above which a candidate counts as "rising"

# Discovery is led by *movement corroborated by breadth*, not by raw magnitude.
# Novelty + curiosity + specificity are first-class so unique/interesting
# material can outrank yet another Iran/Fed/AI-credit rehash. See ITERATION_LOG.
MIN_RISING_COUNT = 5
VELOCITY_CAP = 3.0

_W_MOMENTUM = 0.70
_W_SIGNIFICANCE = 0.08
_W_NOVELTY = 0.95       # product differentiator
_W_CURIOSITY = 0.55     # science / knowledge / discovery-shaped keys
_W_SPECIFICITY = 0.70   # event/story grain over mega-themes
_W_STANDING = 0.55      # subtract — chronic tags without novelty

# Theme/key fragments that signal "new human knowledge / cool feat" material.
_CURIOSITY_MARKERS = (
    "SCIENCE", "SPACE", "ASTRONOM", "BIOLOG", "PHYSICS", "CHEMIST", "GENOME",
    "GENETIC", "CRISPR", "QUANTUM", "TELESCOPE", "FOSSIL", "DINOSAUR", "ARCHAEO",
    "MATH", "MATHEMAT", "CONJECTURE", "THEOREM", "NEURO", "CLIMATE_SCIENCE",
    "TECH_SCIENCE", "INNOVATION", "MEDICAL", "HEALTH_RESEARCH", "PALEONTO",
    "COSMOLOG", "PARTICLE", "MICROSCOP", "EXOPLANET", "DNA_", "RNA_",
    "PEER-REVIEW", "PEER_REVIEW", "BREAKTHROUGH", "DISCOVER",
)


@dataclass(frozen=True)
class ScoredCandidate:
    stats: CandidateStats
    velocity: float | None
    rising: bool
    novel: bool
    curiosity: float
    specificity: float
    standing: float
    score: float
    reasons: tuple[str, ...]


def score_candidates(
    stats: list[CandidateStats], memory: RollingMemory
) -> list[ScoredCandidate]:
    """Attach velocity/novelty/curiosity/specificity and a blended score."""
    return [_score_one(s, memory) for s in stats]


def _curiosity_score(stats: CandidateStats) -> float:
    """0..1 — science/knowledge/discovery shape (not PR fluff)."""
    if getattr(stats, "pillar", None) == "science":
        return 1.0
    blob = f"{stats.full_key} {stats.key}".upper()
    hits = sum(1 for m in _CURIOSITY_MARKERS if m in blob)
    if hits >= 2:
        return 1.0
    if hits == 1:
        return 0.75
    return 0.0


def _specificity_score(stats: CandidateStats) -> float:
    """0..1 — how event/story-shaped vs standing mega-tag."""
    kind = stats.kind
    if kind == "story":
        # URL-slug headlines: reward longer concrete phrases.
        n = len(stats.key.split())
        return min(1.0, 0.55 + 0.05 * n)
    if kind == "event":
        # Actor × action — demote mega-actor + generic war tags that slip through.
        actor, _, action = stats.key.partition(" :: ")
        action_l = action.casefold().strip()
        weak = action_l in {
            "armedconflict", "military", "war", "disaster implied", "kill",
            "political violence and war", "negotiations", "protest",
        }
        mega = actor.casefold().strip() in {
            "united states", "donald trump", "vladimir putin", "china", "russia",
            "european union", "union european", "nato", "iran", "israel",
        }
        if weak and mega and " + " not in actor:
            return 0.12
        if weak and " + " not in actor:
            return 0.35
        return 0.95 if " + " in actor else 0.85
    if kind in ("person", "organization"):
        tokens = [t for t in stats.key.replace(",", " ").split() if t]
        return min(1.0, 0.35 + 0.15 * len(tokens))
    # themes
    if is_broad_theme(stats.key):
        return 0.05
    parts = [p for p in stats.key.split("_") if p and not p.isdigit() and len(p) > 2]
    # Long multi-part theme codes are more specific than one mega code.
    return min(0.75, 0.12 * max(1, len(parts)))


def _standing_penalty(stats: CandidateStats, memory: RollingMemory, novel: bool) -> float:
    """0..1 — chronic baseline without novelty (standing topic tax)."""
    if novel or not memory.has_history:
        return 0.0
    if stats.kind in ("story", "event"):
        # Stories/events still get a light tax if hammered every batch.
        base = memory.baseline(stats.full_key)
        if base < 6:
            return 0.0
        return min(0.6, base / 50.0)
    if stats.kind == "theme" and is_broad_theme(stats.key):
        base = memory.baseline(stats.full_key)
        return min(1.0, 0.45 + base / 40.0)
    base = memory.baseline(stats.full_key)
    if base < 10:
        return 0.0
    return min(0.85, base / 35.0)


def _score_one(stats: CandidateStats, memory: RollingMemory) -> ScoredCandidate:
    velocity = _velocity(stats, memory)
    novel = memory.has_history and not memory.seen(stats.full_key)
    # "Rising" needs both real acceleration and enough support to mean something.
    # Story/event candidates can rise on smaller counts (grain is scarcer).
    min_rising = 2 if stats.kind in ("story", "event") else MIN_RISING_COUNT
    rising = (
        velocity is not None
        and velocity >= RISING_THRESHOLD
        and stats.count >= min_rising
    )
    curiosity = _curiosity_score(stats)
    specificity = _specificity_score(stats)
    standing = _standing_penalty(stats, memory, novel)

    breadth = log1p(len(stats.languages))
    gated_velocity = (
        min(max(velocity or 0.0, 0.0), VELOCITY_CAP)
        if stats.count >= min_rising
        else 0.0
    )
    momentum = breadth * gated_velocity
    significance = log1p(stats.count) + 0.5 * log1p(stats.source_spread)

    # Story headlines are the grain we want; events are secondary (often still broad).
    if stats.kind == "story":
        kind_bonus = 0.55
    elif stats.kind == "event":
        kind_bonus = 0.20
    else:
        kind_bonus = 0.0

    score = (
        _W_MOMENTUM * momentum
        + _W_SIGNIFICANCE * significance
        + _W_NOVELTY * (1.0 if novel else 0.0)
        + _W_CURIOSITY * curiosity
        + _W_SPECIFICITY * specificity
        + kind_bonus
        - _W_STANDING * standing
    )
    # Floor broad themes that somehow still score high on pure volume.
    if stats.kind == "theme" and is_broad_theme(stats.key) and specificity < 0.2:
        score *= 0.55

    return ScoredCandidate(
        stats=stats,
        velocity=velocity,
        rising=rising,
        novel=novel,
        curiosity=curiosity,
        specificity=specificity,
        standing=standing,
        score=round(score, 4),
        reasons=_reasons(stats, rising, novel, curiosity, specificity, standing),
    )


def _velocity(stats: CandidateStats, memory: RollingMemory) -> float | None:
    if not memory.has_history:
        return None  # no baseline yet
    base = memory.baseline(stats.full_key)
    return round((stats.count - base) / (base + SMOOTHING), 3)


def _reasons(
    stats: CandidateStats,
    rising: bool,
    novel: bool,
    curiosity: float,
    specificity: float,
    standing: float,
) -> tuple[str, ...]:
    reasons: list[str] = []
    if rising:
        reasons.append("rising")
    if novel:
        reasons.append("novel")
    if curiosity >= 0.75:
        reasons.append("curiosity")
    if stats.kind in ("story", "event") or specificity >= 0.75:
        reasons.append("specific")
    if standing >= 0.5:
        reasons.append("standing")
    if "eng" not in stats.languages:
        reasons.append("non-english")
    if len(stats.languages) >= 5:
        reasons.append("cross-language")
    if stats.avg_tone is not None and stats.avg_tone <= -5:
        reasons.append("negative-tone")
    return tuple(reasons)


def _is_protected(candidate: ScoredCandidate) -> bool:
    """Margins we refuse to let volume crowd out."""
    return (
        candidate.rising
        or candidate.novel
        or candidate.curiosity >= 0.75
        or candidate.specificity >= 0.75
        or candidate.stats.kind in ("story", "event")
        or "eng" not in candidate.stats.languages
    )


# Two candidates whose supporting records overlap this much are treated as the
# same information object (co-occurring entities/themes of one story).
OVERLAP_THRESHOLD = 0.5
MAX_RELATED = 8


@dataclass
class Selection:
    """A chosen representative plus the co-occurring candidates folded into it."""

    candidate: ScoredCandidate
    related: list[str]


def _jaccard(a: frozenset[int], b: frozenset[int]) -> float:
    if not a or not b:
        return 0.0
    inter = len(a & b)
    return inter / (len(a) + len(b) - inter)


def _dedupe(ranked: list[ScoredCandidate]) -> list[Selection]:
    """Collapse co-occurring candidates: highest-scoring is the representative,
    the rest attach as ``related`` (a story = one entry, with its entities)."""
    reps: list[Selection] = []
    for candidate in ranked:
        host = next(
            (
                rep
                for rep in reps
                if _jaccard(rep.candidate.stats.support, candidate.stats.support)
                >= OVERLAP_THRESHOLD
            ),
            None,
        )
        if host is not None:
            if len(host.related) < MAX_RELATED and candidate.stats.key not in host.related:
                host.related.append(candidate.stats.key)
            continue
        reps.append(Selection(candidate=candidate, related=[]))
    return reps


def select(scored: list[ScoredCandidate], *, top: int, quota: int) -> list[Selection]:
    """Deduped top ``top`` by score, reserving ``quota`` slots for protected margins.

    Preference: when filling the primary band, prefer story/event kinds so the
    shortlist is not all abstract tags even when scores are close.
    """
    ranked = sorted(
        scored,
        key=lambda c: (
            c.score,
            1 if c.stats.kind in ("story", "event") else 0,
            c.specificity,
        ),
        reverse=True,
    )
    reps = _dedupe(ranked)

    primary = reps[: max(top - quota, 0)]
    chosen = {s.candidate.stats.full_key for s in primary}

    reserved = [
        s
        for s in reps
        if s.candidate.stats.full_key not in chosen and _is_protected(s.candidate)
    ][:quota]
    chosen.update(s.candidate.stats.full_key for s in reserved)

    backfill = [s for s in reps if s.candidate.stats.full_key not in chosen]
    result = primary + reserved
    result += backfill[: top - len(result)]
    return sorted(result, key=lambda s: s.candidate.score, reverse=True)
