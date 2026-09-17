"""
``newsroom pause`` — stop a run between stages so it can be picked up later.

Killing a rail mid-stage is safe for the artifacts already on disk, but it wastes whatever
that stage had spent: a profile three minutes into research dies with nothing to show, and
``resume`` restarts it. Pausing instead waits for the current stage to FINISH, writes its
artifact, and exits — which is exactly the state ``resume`` is built to continue from.

The request is a FILE, for the same reason radar's stop is: pausing must not depend on the
run being healthy, on a signal arriving, or on anything being reachable. The rail checks for
it at each stage boundary, which is the only point where stopping is free.

This is a PAUSE, not a cancel. Nothing is discarded, the run directory stays exactly as the
last completed stage left it, and ``newsroom resume`` continues from the next unpaid stage.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

PAUSE_FILE = Path("runs_data") / "newsroom_run.pause"


def requested() -> bool:
    return PAUSE_FILE.exists()


def request() -> None:
    PAUSE_FILE.parent.mkdir(parents=True, exist_ok=True)
    PAUSE_FILE.write_text("pause requested", encoding="utf-8")


def clear() -> None:
    PAUSE_FILE.unlink(missing_ok=True)


class RunPaused(RuntimeError):
    """Raised at a stage boundary when a pause has been requested."""


def add_parser(sub: Any) -> None:
    p = sub.add_parser(
        "pause", help="stop the running rail at the next stage boundary (resumable)")
    p.add_argument("--clear", action="store_true",
                   help="cancel a pending pause request instead of making one")
    p.set_defaults(handler=run_pause)


def _live_holder() -> Any:
    """The rail currently holding the single-flight lock, if one is actually alive."""
    from .single_flight import _pid_alive, _read_holder, lock_path

    holder = _read_holder(lock_path())
    return holder if holder and _pid_alive(holder.pid) else None


def run_pause(args: Any) -> int:
    if args.clear:
        clear()
        print(json.dumps({"paused": False, "note": "pause request cleared"}, indent=2))
        return 0

    holder = _live_holder()
    request()
    print(json.dumps({
        "pause_requested": True,
        "running": bool(holder),
        "pid": holder.pid if holder else None,
        "note": (
            "the rail will finish the stage it is in, write that artifact, and exit — then "
            "`newsroom resume` continues from the next unpaid stage"
            if holder else
            "nothing is running; the request will apply to the next run that starts"
        ),
    }, indent=2))
    return 0
