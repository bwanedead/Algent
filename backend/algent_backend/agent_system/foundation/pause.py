"""
The pause signal — a file, checked at every safe point in a run.

A request is a FILE for the same reason radar's stop is: pausing must not depend on the run being
healthy, on a signal arriving, or on anything being reachable. ``newsroom pause`` writes it; the
run checks it at each CHECKPOINT and unwinds cleanly when it is there.

A checkpoint is a point where the work so far is already on disk in a form ``newsroom resume``
picks up — between rail stages, between enrichment lanes, after each editorial step. Stages run
twenty to thirty minutes, so checking only between them made a pause feel like nothing happened;
checkpoints inside them make it land within one step.

Lives in foundation so any stage can honour it without importing the CLI that requests it.
"""

from __future__ import annotations

from pathlib import Path

PAUSE_FILE = Path("runs_data") / "newsroom_run.pause"


class RunPaused(RuntimeError):
    """Raised at a checkpoint when a pause has been requested."""


def requested() -> bool:
    return PAUSE_FILE.exists()


def request() -> None:
    PAUSE_FILE.parent.mkdir(parents=True, exist_ok=True)
    PAUSE_FILE.write_text("pause requested", encoding="utf-8")


def clear() -> None:
    PAUSE_FILE.unlink(missing_ok=True)


def checkpoint(where: str) -> None:
    """Stop here if a pause was requested. Call only where the work so far is on disk."""
    if requested():
        raise RunPaused(f"paused at {where}")
