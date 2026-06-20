"""
Rolling memory — the small cross-batch state that makes velocity possible.

Velocity and novelty are the highest-value discovery signals, and both need a
*memory* of recent batches. But that memory is tiny: just per-candidate counts
for the last K batches — never the raw records. This is the one thing the
pipeline retains; everything else streams through and is dropped.

Pure data + load/save at the edges. ``RollingMemory`` answers two questions the
ranking layer asks — "what's the baseline for this key?" and "have we seen it
before?" — and ``with_batch`` folds a new batch in, trimming to the window.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

# How many recent batches to keep for baselines. Wide enough to smooth a single
# quiet batch, short enough that "rising" still means *recently*.
DEFAULT_WINDOW = 8


@dataclass(frozen=True)
class BatchAggregate:
    """One past batch, reduced to per-candidate counts."""

    batch_id: str
    counts: dict[str, int]


@dataclass(frozen=True)
class RollingMemory:
    """Recent batches for one source, oldest first. The current batch is excluded."""

    source: str
    batches: tuple[BatchAggregate, ...] = ()

    @property
    def has_history(self) -> bool:
        return bool(self.batches)

    def baseline(self, key: str) -> float:
        """Mean count for ``key`` across remembered batches (0 if never seen)."""
        if not self.batches:
            return 0.0
        return sum(b.counts.get(key, 0) for b in self.batches) / len(self.batches)

    def seen(self, key: str) -> bool:
        return any(key in b.counts for b in self.batches)

    def with_batch(
        self, batch_id: str, counts: dict[str, int], *, window: int = DEFAULT_WINDOW
    ) -> RollingMemory:
        """Return a new memory with ``batch_id`` folded in and trimmed to ``window``."""
        kept = tuple(b for b in self.batches if b.batch_id != batch_id)
        appended = (*kept, BatchAggregate(batch_id=batch_id, counts=dict(counts)))
        return RollingMemory(source=self.source, batches=appended[-window:])


def load_memory(source: str, directory: Path) -> RollingMemory:
    """Read a source's rolling memory; empty memory if none exists yet."""
    path = directory / f"{source}.json"
    if not path.exists():
        return RollingMemory(source=source)
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
        batches = tuple(
            BatchAggregate(batch_id=b["batch_id"], counts=dict(b["counts"]))
            for b in raw.get("batches", [])
        )
        return RollingMemory(source=source, batches=batches)
    except (OSError, ValueError, KeyError):
        return RollingMemory(source=source)


def save_memory(memory: RollingMemory, directory: Path) -> None:
    """Persist a source's rolling memory (small JSON)."""
    directory.mkdir(parents=True, exist_ok=True)
    payload = {
        "source": memory.source,
        "batches": [{"batch_id": b.batch_id, "counts": b.counts} for b in memory.batches],
    }
    (directory / f"{memory.source}.json").write_text(
        json.dumps(payload, indent=2), encoding="utf-8"
    )
