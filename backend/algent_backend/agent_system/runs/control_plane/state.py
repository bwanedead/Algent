"""
Live run state — ``state.json``.

A small, frequently-rewritten snapshot of where a run is right now. Written
atomically so watchers never read a torn file. The event stream is the history;
state.json is only the current photo.
"""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field

from .fsio import atomic_write_text
from .layout import RunPaths

RunLifecycleStatus = Literal["queued", "running", "completed", "failed"]


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


def read_state(paths: RunPaths) -> RunState:
    """Read ``state.json`` (raises ``FileNotFoundError`` if the run is unknown)."""
    return RunState.model_validate_json(paths.state_file.read_text(encoding="utf-8"))
