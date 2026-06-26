"""
``build_digest`` — assemble a :class:`DiscoveryDigest` from parsed records.

The one orchestrating function of the discovery layer: group records by language
(the axis), run each lens within a language, tag themes with their pillar, and
fold the result into the typed contract. Pure and deterministic — same records
in, same digest out.
"""

from __future__ import annotations

from collections import Counter, defaultdict
from datetime import UTC, datetime

from ..sources.records import GkgRecord
from . import lenses
from .contract import DiscoveryDigest, LanguageDigest, ThemeStat, TonedTheme
from .pillars import pillar_for_theme


def build_digest(
    records: list[GkgRecord], *, source: str, batch_id: str
) -> DiscoveryDigest:
    """Digest a batch of records, grouped by source language."""
    by_language: dict[str, list[GkgRecord]] = defaultdict(list)
    for record in records:
        by_language[record.language].append(record)

    languages = [
        _language_digest(language, group)
        for language, group in by_language.items()
    ]
    # Largest language first — the dominant coverage is what an operator scans.
    languages.sort(key=lambda lang: lang.record_count, reverse=True)

    return DiscoveryDigest(
        source=source,
        batch_id=batch_id,
        generated_at=datetime.now(UTC).isoformat(),
        total_records=len(records),
        languages=languages,
    )


def _language_digest(language: str, records: list[GkgRecord]) -> LanguageDigest:
    negative, positive = lenses.tone_lens(records)
    return LanguageDigest(
        language=language,
        record_count=len(records),
        pillar_volume=_pillar_volume(records),
        top_themes=[_theme_stat(t, n) for t, n in lenses.volume_lens(records)],
        rare_themes=[_theme_stat(t, n) for t, n in lenses.rarity_lens(records)],
        most_negative=[_toned(t, tone, n) for t, tone, n in negative],
        most_positive=[_toned(t, tone, n) for t, tone, n in positive],
    )


def _pillar_volume(records: list[GkgRecord]) -> dict[str, int]:
    """Count records touching each pillar at least once."""
    counts: Counter[str] = Counter()
    for record in records:
        pillars = {p for theme in record.themes if (p := pillar_for_theme(theme))}
        counts.update(pillars)
    return dict(counts)


def _theme_stat(theme: str, count: int) -> ThemeStat:
    return ThemeStat(theme=theme, count=count, pillar=pillar_for_theme(theme))


def _toned(theme: str, avg_tone: float, count: int) -> TonedTheme:
    return TonedTheme(
        theme=theme,
        avg_tone=round(avg_tone, 3),
        count=count,
        pillar=pillar_for_theme(theme),
    )
