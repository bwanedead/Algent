"""
Ranking — score candidates and select a shortlist that resists the headline rut.

Two steps:

- **score** each candidate by blending the signals that matter for discovery:
  momentum (movement + breadth), a light significance floor, **novelty** (new to
  our memory — our asset vs wire sameness), and **curiosity** (science / knowledge
  / discovery-shaped themes — feats and new human knowledge).
- **select** the shortlist with a *protected quota* for rising / novel /
  non-English / science-curiosity margins so loud war-macro cannot crowd them out.

Volume alone is the rut. Novelty and curiosity are boosted, not punished.
"""

from __future__ import annotations

from dataclasses import dataclass
from math import log1p

from .candidates import CandidateStats
from .memory import RollingMemory

# Velocity smoothing: baselines this small or smaller can't manufacture huge
# acceleration from noise. ``(count - base) / (base + SMOOTHING)``.
SMOOTHING = 2.0
RISING_THRESHOLD = 0.5  # velocity at/above which a candidate counts as "rising"

# Discovery is led by *movement corroborated by breadth*, not by raw magnitude.
# Novelty + curiosity are first-class so unique/interesting material can outrank
# yet another Iran/Fed/AI-credit rehash. See ITERATION_LOG.
MIN_RISING_COUNT = 5
VELOCITY_CAP = 3.0

_W_MOMENTUM = 0.85
_W_SIGNIFICANCE = 0.10
_W_NOVELTY = 0.95       # was 0.30 — novelty is the product differentiator
_W_CURIOSITY = 0.55     # science / knowledge / discovery-shaped keys

# Theme/key fragments that signal "new human knowledge / cool feat" material.
_CURIOSITY_MARKERS = (
    "SCIENCE", "SPACE", "ASTRONOM", "BIOLOG", "PHYSICS", "CHEMIST", "GENOME",
    "GENETIC", "CRISPR", "QUANTUM", "TELESCOPE", "FOSSIL", "DINOSAUR", "ARCHAEO",
    "MATH", "MATHEMAT", "CONJECTURE", "THEOREM", "NEURO", "CLIMATE_SCIENCE",
    "TECH_SCIENCE", "INNOVATION", "MEDICAL", "HEALTH_RESEARCH", "PALEONTO",
    "COSMOLOG", "PARTICLE", "MICROSCOP", "EXOPLANET", "DNA_", "RNA_",
)


@dataclass(frozen=True)
class ScoredCandidate:
    stats: CandidateStats
    velocity: float | None
    rising: bool
    novel: bool
    curiosity: float
    score: float
    reasons: tuple[str, ...]


def score_candidates(
    stats: list[CandidateStats], memory: RollingMemory
) -> list[ScoredCandidate]:
    """Attach velocity/novelty/curiosity and a blended score to every candidate."""
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


def _score_one(stats: CandidateStats, memory: RollingMemory) -> ScoredCandidate:
    velocity = _velocity(stats, memory)
    novel = memory.has_history and not memory.seen(stats.full_key)
    # "Rising" needs both real acceleration and enough support to mean something.
    rising = (
        velocity is not None
        and velocity >= RISING_THRESHOLD
        and stats.count >= MIN_RISING_COUNT
    )
    curiosity = _curiosity_score(stats)

    breadth = log1p(len(stats.languages))
    gated_velocity = min(max(velocity or 0.0, 0.0), VELOCITY_CAP) if stats.count >= MIN_RISING_COUNT else 0.0
    momentum = breadth * gated_velocity
    significance = log1p(stats.count) + 0.5 * log1p(stats.source_spread)

    score = (
        _W_MOMENTUM * momentum
        + _W_SIGNIFICANCE * significance
        + _W_NOVELTY * (1.0 if novel else 0.0)
        + _W_CURIOSITY * curiosity
    )
    return ScoredCandidate(
        stats=stats,
        velocity=velocity,
        rising=rising,
        novel=novel,
        curiosity=curiosity,
        score=round(score, 4),
        reasons=_reasons(stats, rising, novel, curiosity),
    )


def _velocity(stats: CandidateStats, memory: RollingMemory) -> float | None:
    if not memory.has_history:
        return None  # no baseline yet
    base = memory.baseline(stats.full_key)
    return round((stats.count - base) / (base + SMOOTHING), 3)


def _reasons(
    stats: CandidateStats, rising: bool, novel: bool, curiosity: float,
) -> tuple[str, ...]:
    reasons: list[str] = []
    if rising:
        reasons.append("rising")
    if novel:
        reasons.append("novel")
    if curiosity >= 0.75:
        reasons.append("curiosity")
    if "eng" not in stats.languages:
        reasons.append("non-english")
    if len(stats.languages) >= 5:
        reasons.append("cross-language")
    if stats.avg_tone is not None and stats.avg_tone <= -5:
        reasons.append("negative-tone")
    return tuple(reasons)


def _is_protected(candidate: ScoredCandidate) -> bool:
    """The margins we refuse to let volume crowd out — including science/curiosity."""
    return (
        candidate.rising
        or candidate.novel
        or candidate.curiosity >= 0.75
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
    """Deduped top ``top`` by score, reserving ``quota`` slots for protected margins."""
    ranked = sorted(scored, key=lambda c: c.score, reverse=True)
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
