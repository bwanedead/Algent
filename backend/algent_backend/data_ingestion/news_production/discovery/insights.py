"""
Insights orchestrator — assemble the deterministic :class:`InsightsReport`.

Ties the discovery layers together for one batch: extract candidates, score them
against the rolling memory, select the rut-resistant shortlist, and build the
per-language "world news" view. Returns the report *and* this batch's counts, so
the caller can fold them into memory only after a successful build.

Pure: memory is passed in, no file I/O here. The caller owns persistence.
"""

from __future__ import annotations

from collections import Counter, defaultdict
from datetime import UTC, datetime

from ..sources.records import GkgRecord
from .candidates import CandidateStats, extract_candidates
from .memory import RollingMemory
from .noise import is_boilerplate_theme, is_noise_entity
from .ranking import Selection, score_candidates, select
from .report import Candidate, InsightsReport, LanguageInsights

DEFAULT_TOP = 40
DEFAULT_QUOTA = 10  # protected slots within the shortlist
DEFAULT_PER_LANGUAGE_TOP = 8


def build_insights(
    records: list[GkgRecord],
    *,
    source: str,
    batch_id: str,
    memory: RollingMemory,
    top: int = DEFAULT_TOP,
    quota: int = DEFAULT_QUOTA,
    per_language_top: int = DEFAULT_PER_LANGUAGE_TOP,
) -> tuple[InsightsReport, dict[str, int]]:
    """Build the report for a batch; also return its per-candidate counts."""
    stats = extract_candidates(records)
    scored = score_candidates(stats, memory)
    shortlist = select(scored, top=top, quota=quota)

    rising_keys = {
        s.candidate.stats.full_key for s in shortlist if s.candidate.rising or s.candidate.novel
    }
    report = InsightsReport(
        source=source,
        batch_id=batch_id,
        generated_at=datetime.now(UTC).isoformat(),
        total_records=len(records),
        has_velocity_baseline=memory.has_history,
        candidates=[_to_model(c) for c in shortlist],
        by_language=_language_view(records, rising_keys, per_language_top),
    )
    counts = {s.full_key: s.count for s in stats}
    return report, counts


def _to_model(selection: Selection) -> Candidate:
    c = selection.candidate
    s = c.stats
    return Candidate(
        key=s.key,
        kind=s.kind,
        pillar=s.pillar,
        count=s.count,
        velocity=c.velocity,
        rising=c.rising,
        novel=c.novel,
        language_count=len(s.languages),
        languages=list(s.languages),
        avg_tone=s.avg_tone,
        source_spread=s.source_spread,
        score=c.score,
        reasons=list(c.reasons),
        related=list(selection.related),
    )


def _language_view(
    records: list[GkgRecord], rising_keys: set[str], per_language_top: int
) -> list[LanguageInsights]:
    """Per-language "what's big here" — the world-news axis.

    Counts themes + entities within each language and lists the biggest; any of
    those that are globally rising/novel are flagged. (Per-language *velocity* is
    the next iteration; this gives the per-language *volume* read today.)
    """
    by_lang_counts: dict[str, Counter[str]] = defaultdict(Counter)
    record_counts: Counter[str] = Counter()
    for record in records:
        record_counts[record.language] += 1
        for kind, key in _record_keys(record):
            by_lang_counts[record.language][f"{kind}:{key}"] += 1

    views = []
    for language, counts in by_lang_counts.items():
        top_keys = [key for key, _ in counts.most_common(per_language_top)]
        views.append(
            LanguageInsights(
                language=language,
                record_count=record_counts[language],
                top=[_display(k) for k in top_keys],
                rising=[_display(k) for k in top_keys if k in rising_keys],
            )
        )
    views.sort(key=lambda v: v.record_count, reverse=True)
    return views


def _record_keys(record: GkgRecord) -> set[tuple[str, str]]:
    keys: set[tuple[str, str]] = set()
    keys.update(("theme", t) for t in record.themes if not is_boilerplate_theme(t))
    keys.update(("person", p) for p in record.persons if not is_noise_entity(p))
    keys.update(("organization", o) for o in record.organizations if not is_noise_entity(o))
    return keys


def _display(full_key: str) -> str:
    """Drop the ``kind:`` prefix for the human/agent-facing per-language lists."""
    return full_key.split(":", 1)[1] if ":" in full_key else full_key


# Re-exported for callers that want the raw stats (e.g. tests).
__all__ = ["build_insights", "CandidateStats"]
