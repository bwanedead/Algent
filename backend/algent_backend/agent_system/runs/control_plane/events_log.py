"""
Event log — append-only ``events.jsonl`` writer/reader.

The writer assigns sequence numbers and timestamps so emitters only say *what
happened*. One process owns a run's log (the process executing the run), so a
plain append is safe; readers tolerate a partial trailing line.
"""

from __future__ import annotations

import json
from datetime import UTC, datetime
from typing import Any

from algent_backend.agent_system.runs.events import RunEvent

from .layout import RunPaths


class RunEventLog:
    """Appends RunEvents to one run's ``events.jsonl``."""

    def __init__(self, paths: RunPaths, run_id: str, start_seq: int = 0) -> None:
        self._paths = paths
        self._run_id = run_id
        # start_seq lets a second writer (e.g. the stop command) continue the
        # sequence after the run's own events rather than colliding from 1.
        self._seq = start_seq
        self._appended: list[RunEvent] = []

    def append(self, event_type: str, payload: dict[str, Any] | None = None) -> RunEvent:
        self._seq += 1
        event = RunEvent(
            seq=self._seq,
            ts=datetime.now(UTC).isoformat(),
            run_id=self._run_id,
            type=event_type,
            payload=payload or {},
        )
        self._paths.events_file.parent.mkdir(parents=True, exist_ok=True)
        # default=str: payloads may carry non-JSON values (message objects, paths);
        # the log keeps a string rendering rather than refusing the fact.
        line = json.dumps(event.model_dump(), ensure_ascii=False, default=str)
        with self._paths.events_file.open("a", encoding="utf-8") as handle:
            handle.write(line + "\n")
        self._appended.append(event)
        return event

    @property
    def appended(self) -> list[RunEvent]:
        """Events appended by this writer (the live in-memory view)."""
        return self._appended


def read_events(paths: RunPaths) -> list[RunEvent]:
    """Read all events for a run; skips unparseable (torn) lines."""
    if not paths.events_file.exists():
        return []
    events: list[RunEvent] = []
    for line in paths.events_file.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            events.append(RunEvent.model_validate(json.loads(line)))
        except Exception:
            continue
    return events
