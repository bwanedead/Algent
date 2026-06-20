"""
Candidate extraction — turn a batch of records into scoreable *topics*.

Theme codes are good for pillars and cross-language reach, but the things worth
a story live at the **entity** level (the person/org) too. So a candidate is any
theme or named entity, aggregated across the batch with the facts ranking needs:
how many records carry it, in which languages, its average tone, and how many
distinct outlets ran it (spread separates "one outlet hammering it" from "the
world is covering it").

Pure and deterministic — records in, candidate stats out. No scoring, no I/O;
that is the ranking layer's job.
"""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass

from ..sources.records import GkgRecord
from .pillars import is_boilerplate_theme, pillar_for_theme

# Ignore items carried by fewer than this many records — pure noise otherwise.
DEFAULT_MIN_COUNT = 3


@dataclass(frozen=True, slots=True)
class CandidateStats:
    """Aggregated facts about one candidate across a batch (pre-scoring)."""

    kind: str  # "theme" | "person" | "organization"
    key: str
    count: int
    languages: tuple[str, ...]
    avg_tone: float | None
    source_spread: int
    pillar: str | None

    @property
    def full_key(self) -> str:
        """Stable identity across batches (used as the rolling-memory key)."""
        return f"{self.kind}:{self.key}"


@dataclass
class _Accumulator:
    count: int = 0
    tone_sum: float = 0.0
    tone_n: int = 0

    def __post_init__(self) -> None:
        self.languages: set[str] = set()
        self.sources: set[str] = set()


def extract_candidates(
    records: Iterable[GkgRecord], *, min_count: int = DEFAULT_MIN_COUNT
) -> list[CandidateStats]:
    """Aggregate records into candidate stats, dropping anything below ``min_count``."""
    acc: dict[tuple[str, str], _Accumulator] = {}
    for record in records:
        for kind, key in _items(record):
            entry = acc.setdefault((kind, key), _Accumulator())
            entry.count += 1
            entry.languages.add(record.language)
            if record.source_name:
                entry.sources.add(record.source_name)
            if record.tone is not None:
                entry.tone_sum += record.tone
                entry.tone_n += 1

    stats = [
        CandidateStats(
            kind=kind,
            key=key,
            count=entry.count,
            languages=tuple(sorted(entry.languages)),
            avg_tone=round(entry.tone_sum / entry.tone_n, 3) if entry.tone_n else None,
            source_spread=len(entry.sources),
            pillar=pillar_for_theme(key) if kind == "theme" else None,
        )
        for (kind, key), entry in acc.items()
        if entry.count >= min_count
    ]
    stats.sort(key=lambda s: s.count, reverse=True)
    return stats


def _items(record: GkgRecord) -> set[tuple[str, str]]:
    """The distinct (kind, key) pairs a single record contributes (deduped).

    Boilerplate themes are dropped here so they never reach scoring.
    """
    items: set[tuple[str, str]] = set()
    items.update(("theme", t) for t in record.themes if not is_boilerplate_theme(t))
    items.update(("person", p) for p in record.persons)
    items.update(("organization", o) for o in record.organizations)
    return items
