"""
Ranking — score candidates and select a shortlist that resists the headline rut.

Two steps:

- **score** each candidate by blending the signals that matter for discovery:
  significance (volume + outlet spread), velocity (acceleration vs the rolling
  baseline), cross-language reach, and novelty. Volume alone is the rut, so it is
  only one term and not the dominant one.
- **select** the shortlist with a *protected quota*: most slots go to the top
  blended scores, but a reserved fraction is held for rising / novel /
  non-English-only candidates so the loud incumbents can't crowd out the margins
  where real discovery lives.

Pure functions over :class:`CandidateStats` + :class:`RollingMemory`.
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

# Blend weights (significance, velocity, cross-language, novelty).
_W_SIGNIFICANCE = 0.40
_W_VELOCITY = 0.30
_W_CROSS_LANGUAGE = 0.20
_W_NOVELTY = 0.10


@dataclass(frozen=True)
class ScoredCandidate:
    stats: CandidateStats
    velocity: float | None
    rising: bool
    novel: bool
    score: float
    reasons: tuple[str, ...]


def score_candidates(
    stats: list[CandidateStats], memory: RollingMemory
) -> list[ScoredCandidate]:
    """Attach velocity/novelty and a blended score to every candidate."""
    return [_score_one(s, memory) for s in stats]


def _score_one(stats: CandidateStats, memory: RollingMemory) -> ScoredCandidate:
    velocity = _velocity(stats, memory)
    novel = memory.has_history and not memory.seen(stats.full_key)
    rising = velocity is not None and velocity >= RISING_THRESHOLD

    score = (
        _W_SIGNIFICANCE * (log1p(stats.count) + 0.5 * log1p(stats.source_spread))
        + _W_VELOCITY * max(velocity or 0.0, 0.0)
        + _W_CROSS_LANGUAGE * log1p(len(stats.languages))
        + _W_NOVELTY * (1.0 if novel else 0.0)
    )
    return ScoredCandidate(
        stats=stats,
        velocity=velocity,
        rising=rising,
        novel=novel,
        score=round(score, 4),
        reasons=_reasons(stats, rising, novel),
    )


def _velocity(stats: CandidateStats, memory: RollingMemory) -> float | None:
    if not memory.has_history:
        return None  # no baseline yet
    base = memory.baseline(stats.full_key)
    return round((stats.count - base) / (base + SMOOTHING), 3)


def _reasons(stats: CandidateStats, rising: bool, novel: bool) -> tuple[str, ...]:
    reasons: list[str] = []
    if rising:
        reasons.append("rising")
    if novel:
        reasons.append("novel")
    if "eng" not in stats.languages:
        reasons.append("non-english")
    if len(stats.languages) >= 5:
        reasons.append("cross-language")
    if stats.avg_tone is not None and stats.avg_tone <= -5:
        reasons.append("negative-tone")
    return tuple(reasons)


def _is_protected(candidate: ScoredCandidate) -> bool:
    """The margins we refuse to let volume crowd out."""
    return (
        candidate.rising
        or candidate.novel
        or "eng" not in candidate.stats.languages
    )


def select(
    scored: list[ScoredCandidate], *, top: int, quota: int
) -> list[ScoredCandidate]:
    """Top ``top`` by score, but reserve ``quota`` slots for protected candidates."""
    ranked = sorted(scored, key=lambda c: c.score, reverse=True)
    primary = ranked[: max(top - quota, 0)]
    chosen_keys = {c.stats.full_key for c in primary}

    reserved = [
        c for c in ranked if c.stats.full_key not in chosen_keys and _is_protected(c)
    ][:quota]
    chosen_keys.update(c.stats.full_key for c in reserved)

    # Backfill any unused quota with the next-best overall, so we always return
    # up to ``top``.
    backfill = [c for c in ranked if c.stats.full_key not in chosen_keys]
    result = primary + reserved
    result += backfill[: top - len(result)]
    return sorted(result, key=lambda c: c.score, reverse=True)
