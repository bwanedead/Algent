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
from ..topic_filters import is_sports_text
from .noise import is_boilerplate_theme, is_noise_entity
from .pillars import pillar_for_theme

# Ignore items carried by fewer than this many records — pure noise otherwise.
DEFAULT_MIN_COUNT = 3
# How many example article URLs to keep per candidate (grounding, not exhaustive).
_MAX_EXAMPLES = 3


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
    # Indices of the records that mention it — the evidence set used to detect
    # co-occurring candidates (entities of the same story) during selection.
    support: frozenset[int] = frozenset()
    # A few example article URLs (from the supporting records) so the agent can
    # free-fetch real sources before reaching for any paid surface.
    examples: tuple[str, ...] = ()

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
        self.support: set[int] = set()
        self.examples: list[str] = []  # a few distinct article URLs (capped)


def extract_candidates(
    records: Iterable[GkgRecord], *, min_count: int = DEFAULT_MIN_COUNT
) -> list[CandidateStats]:
    """Aggregate records into candidate stats, dropping anything below ``min_count``."""
    acc: dict[tuple[str, str], _Accumulator] = {}
    for index, record in enumerate(records):
        for kind, key in _items(record):
            entry = acc.setdefault((kind, key), _Accumulator())
            entry.count += 1
            entry.support.add(index)
            entry.languages.add(record.language)
            if record.source_name:
                entry.sources.add(record.source_name)
            if record.url and len(entry.examples) < _MAX_EXAMPLES and record.url not in entry.examples:
                entry.examples.append(record.url)
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
            support=frozenset(entry.support),
            examples=tuple(entry.examples),
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
    items.update(
        ("person", p) for p in record.persons
        if not is_noise_entity(p) and not is_sports_text(p)
    )
    items.update(
        ("organization", o) for o in record.organizations
        if not is_noise_entity(o) and not is_sports_text(o)
    )
    return items
