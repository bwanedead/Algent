"""
Lenses — the deterministic ways we look at a batch of records.

Each lens is a pure function over a list of records (already narrowed to one
language, since language is an axis, not a lens) returning small ranked tuples.
The digest layer assembles these into the typed contract. Three v1 lenses:

- **volume**  — the loudest themes (what the world is covering most). The
  baseline "headline basket".
- **rarity**  — themes that barely appear. Deliberately the counterweight to
  volume: the under-covered / niche signal that keeps discovery out of the
  headline rut.
- **tone**    — the most negative and most positive themes by average document
  tone (where coverage is alarmed vs. celebratory).

Lenses intentionally know nothing about pillars, I/O, or models.
"""

from __future__ import annotations

from collections import Counter, defaultdict
from collections.abc import Iterable

from ..sources.records import GkgRecord


def theme_counts(records: Iterable[GkgRecord]) -> Counter[str]:
    """Raw frequency of every theme across the records — the shared substrate."""
    counts: Counter[str] = Counter()
    for record in records:
        counts.update(set(record.themes))  # one article counts once per theme
    return counts


def volume_lens(records: Iterable[GkgRecord], *, top: int = 20) -> list[tuple[str, int]]:
    """The ``top`` most frequent themes, most-covered first."""
    return theme_counts(records).most_common(top)


def rarity_lens(
    records: Iterable[GkgRecord], *, max_count: int = 2, limit: int = 30
) -> list[tuple[str, int]]:
    """Themes appearing at most ``max_count`` times — the under-covered tail.

    Sorted rarest-first then alphabetically so the output is stable. A single
    long tail of one-off coded themes is exactly where novel topics hide.
    """
    counts = theme_counts(records)
    rare = [(theme, n) for theme, n in counts.items() if n <= max_count]
    rare.sort(key=lambda item: (item[1], item[0]))
    return rare[:limit]


def tone_lens(
    records: Iterable[GkgRecord], *, top: int = 10, min_support: int = 3
) -> tuple[list[tuple[str, float, int]], list[tuple[str, float, int]]]:
    """Average tone per theme. Returns ``(most_negative, most_positive)``.

    Only themes carried by at least ``min_support`` toned articles are ranked,
    so a single shrill outlier can't define a theme's tone.
    """
    totals: dict[str, float] = defaultdict(float)
    seen: Counter[str] = Counter()
    for record in records:
        if record.tone is None:
            continue
        for theme in set(record.themes):
            totals[theme] += record.tone
            seen[theme] += 1

    averaged = [
        (theme, totals[theme] / seen[theme], seen[theme])
        for theme in totals
        if seen[theme] >= min_support
    ]
    most_negative = sorted(averaged, key=lambda item: item[1])[:top]
    most_positive = sorted(averaged, key=lambda item: item[1], reverse=True)[:top]
    return most_negative, most_positive
