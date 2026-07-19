"""
Live run state — ``state.json``.

A small, frequently-rewritten snapshot of where a run is right now. Written
atomically so watchers never read a torn file. The event stream is the history;
state.json is only the current photo.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any, Literal

from pydantic import BaseModel, Field

from .fsio import atomic_write_text
from .layout import RunPaths
from .liveness import process_alive

RunLifecycleStatus = Literal["queued", "running", "completed", "failed", "stopped"]


class RunState(BaseModel):
    """Current snapshot of one run."""

    run_id: str
    agent_id: str
    runtime: str
    status: RunLifecycleStatus
    created_at: str
    updated_at: str
    pid: int | None = None
    input: dict[str, Any] = Field(default_factory=dict)
    max_turns: int | None = None
    error: str | None = None
    # Where the deep trace lives, if LangSmith tracing was active for this run.
    langsmith_project: str | None = None


def write_state(paths: RunPaths, state: RunState) -> None:
    """Atomically write ``state.json``."""
    atomic_write_text(paths.state_file, state.model_dump_json(indent=2))


CRASH_ERROR = ("process is no longer running — the run crashed or its session was disconnected "
                "(a foreground run dies with its terminal; use a background run to survive that)")


def read_state(paths: RunPaths) -> RunState:
    """Read ``state.json``, RECONCILED against reality (raises ``FileNotFoundError`` if unknown).

    A run whose process has vanished must never keep reporting ``running`` — that is the ledger
    lying, and it is exactly what happens when a foreground run's session drops: the child dies
    mid-stage and the last state written says "running" forever. So the check lives here, in the
    read, rather than in each caller: every consumer (status, list, show, watch, the publish step)
    gets the truth without having to remember to ask.

    The correction is persisted, so the run is durably marked failed rather than re-diagnosed on
    every read. Deliberately conservative: only a run that is ``running`` with a KNOWN pid that is
    provably gone is reconciled, and ``process_alive`` errs toward "alive" — we would rather be
    briefly stale than declare a working run dead.
    """
    state = RunState.model_validate_json(paths.state_file.read_text(encoding="utf-8"))
    if state.status == "running" and state.pid is not None and not process_alive(state.pid):
        state = state.model_copy(update={
            "status": "failed",
            "error": state.error or CRASH_ERROR,
            "updated_at": datetime.now(UTC).isoformat(),
        })
        try:
            write_state(paths, state)     # persist the correction; best-effort (read must not fail)
        except OSError:
            pass
    return state
