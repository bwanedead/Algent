"""
RunEvent — the neutral, owned trace record.

One event = one fact about a run, appended to that run's ``events.jsonl``.
This stream is Algent's durable trace regardless of LangSmith: LangSmith holds
the deep payload-level tree (rented), events.jsonl holds what we always keep.

``type`` is an open string on purpose. Known types get constants below, but new
event categories must be able to appear organically without a contract change —
consumers tolerate unknown types. Payloads carry facts, not judgments.

This module is a pure contract: no I/O, no rail imports. Appending lives in
``runs/control_plane/events_log.py``.
"""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field

# Known event types (not exhaustive — see module docstring).
RUN_STARTED = "run.started"
RUN_COMPLETED = "run.completed"
RUN_FAILED = "run.failed"
RUN_STOPPED = "run.stopped"
NODE_COMPLETED = "node.completed"
MODEL_USAGE = "model.usage"
ARTIFACT_WRITTEN = "artifact.written"


class RunEvent(BaseModel):
    """One appended fact in a run's event stream."""

    seq: int
    ts: str
    run_id: str
    type: str
    payload: dict[str, Any] = Field(default_factory=dict)
