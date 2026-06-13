"""
Run ledger — the cross-run index.

Append-only ``runs_index.jsonl`` at the runs-data root: one entry when a run
starts, one when it ends. ``list_runs`` folds entries by run id (latest wins),
so the index is event-sourced and never rewritten in place.

This is the aggregate query surface Algent owns regardless of LangSmith:
"what ran, when, with what outcome, at what token cost".
"""

from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from pydantic import BaseModel, Field

from .layout import index_file


class LedgerEntry(BaseModel):
    """One run's summary row in the cross-run index."""

    run_id: str
    agent_id: str
    runtime: str
    status: str
    created_at: str
    finished_at: str | None = None
    duration_s: float | None = None
    input_tokens: int | None = None
    output_tokens: int | None = None
    artifact_count: int = 0
    error: str | None = None
    extra: dict[str, Any] = Field(default_factory=dict)


class RunLedger:
    """Appends and folds the cross-run index."""

    def __init__(self, root: Path | None = None) -> None:
        self._index = index_file(root)

    def append(self, entry: LedgerEntry) -> None:
        self._index.parent.mkdir(parents=True, exist_ok=True)
        with self._index.open("a", encoding="utf-8") as handle:
            handle.write(entry.model_dump_json() + "\n")

    def list_runs(self) -> list[LedgerEntry]:
        """All runs, one (latest) entry each, newest created first."""
        if not self._index.exists():
            return []
        latest: dict[str, LedgerEntry] = {}
        for line in self._index.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line:
                continue
            try:
                entry = LedgerEntry.model_validate(json.loads(line))
            except Exception:
                continue
            latest[entry.run_id] = entry
        return sorted(latest.values(), key=lambda e: e.created_at, reverse=True)


def utc_now_iso() -> str:
    return datetime.now(UTC).isoformat()
