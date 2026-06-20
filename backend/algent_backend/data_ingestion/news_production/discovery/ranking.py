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

# Discovery is led by *movement corroborated by breadth*, not by raw magnitude.
# A candidate must clear MIN_RISING_COUNT records before its velocity counts (kills
# 0->3 ratio spikes), and velocity is capped so one explosive item can't win on
# ratio alone. Momentum = breadth(languages) x capped-positive-velocity, so a rise
# seen across many languages outranks an isolated single-language spike (the
# principled lever against PR/promo noise). Significance is only a gentle floor —
# it dominates solely at cold start, before any baseline exists. See ITERATION_LOG.
MIN_RISING_COUNT = 5
VELOCITY_CAP = 3.0

_W_MOMENTUM = 1.0
_W_SIGNIFICANCE = 0.12
_W_NOVELTY = 0.30


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
    # "Rising" needs both real acceleration and enough support to mean something.
    rising = (
        velocity is not None
        and velocity >= RISING_THRESHOLD
        and stats.count >= MIN_RISING_COUNT
    )

    breadth = log1p(len(stats.languages))
    gated_velocity = min(max(velocity or 0.0, 0.0), VELOCITY_CAP) if stats.count >= MIN_RISING_COUNT else 0.0
    momentum = breadth * gated_velocity
    significance = log1p(stats.count) + 0.5 * log1p(stats.source_spread)

    score = (
        _W_MOMENTUM * momentum
        + _W_SIGNIFICANCE * significance
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
