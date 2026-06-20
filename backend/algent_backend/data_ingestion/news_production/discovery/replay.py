"""
Replay — run a sequence of batches through the pipeline with accumulating memory.

The evaluation instrument for tuning the deterministic signals: feed an ordered
list of ``(batch_id, records)`` and get back the per-batch :class:`InsightsReport`
sequence, with rolling memory carried forward exactly as production would. That
lets us watch velocity/novelty emerge over real consecutive batches and compare
parameter changes on identical data.

Pure: no I/O, no network. The caller supplies the (already-fetched) batches.
"""

from __future__ import annotations

from collections.abc import Iterable

from ..sources.records import GkgRecord
from .insights import build_insights
from .memory import RollingMemory
from .report import InsightsReport


def replay(
    batches: Iterable[tuple[str, list[GkgRecord]]],
    *,
    source: str,
    memory: RollingMemory | None = None,
    **insight_params: object,
) -> list[InsightsReport]:
    """Build a report per batch, threading rolling memory through the sequence."""
    current = memory or RollingMemory(source=source)
    reports: list[InsightsReport] = []
    for batch_id, records in batches:
        report, counts = build_insights(
            records, source=source, batch_id=batch_id, memory=current, **insight_params
        )
        current = current.with_batch(batch_id, counts)
        reports.append(report)
    return reports
