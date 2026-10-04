"""
``newsroom pause`` — stop a run at its next checkpoint so it can be picked up later.

Checkpoints sit inside stages too (between research lanes, after each editorial step), so a
pause lands within one step, not at the end of a 30-minute stage. ``--now`` kills outright.

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
from typing import Any

# The signal itself lives in foundation so pipeline stages can check it without importing the CLI.
from algent_backend.agent_system.foundation.pause import (  # noqa: F401 — re-exported
    PAUSE_FILE,
    RunPaused,
    clear,
    request,
    requested,
)


def add_parser(sub: Any) -> None:
    p = sub.add_parser(
        "pause", help="stop the running rail at the next stage boundary (resumable)")
    p.add_argument("--clear", action="store_true",
                   help="cancel a pending pause request instead of making one")
    p.add_argument("--now", action="store_true",
                   help="stop immediately (kills the run's process tree); resume redoes only the "
                        "step it was in")
    p.add_argument("--force", action="store_true",
                   help="with --now: kill even while charts are drawing (their grok work is lost)")
    p.set_defaults(handler=run_pause)


def _live_holder() -> Any:
    """The rail currently holding the single-flight lock, if one is actually alive."""
    from .single_flight import _pid_alive, _read_holder, lock_path

    holder = _read_holder(lock_path())
    return holder if holder and _pid_alive(holder.pid) else None


def _charts_drawing() -> bool:
    """A chart worker wrote into its scratch folder in the last two minutes."""
    import time

    from algent_backend.agent_system.agents.newsroom.watchdog import _scratch_activity

    return time.time() - _scratch_activity() < 120


def run_pause(args: Any) -> int:
    if args.clear:
        clear()
        print(json.dumps({"paused": False, "note": "pause request cleared"}, indent=2))
        return 0

    holder = _live_holder()
    drawing = bool(holder) and _charts_drawing()
    if args.now and drawing and not getattr(args, "force", False):
        # Killing mid-chart throws away grok subscription work that a normal pause would keep.
        print(json.dumps({
            "stopped_now": False, "charts_drawing": True,
            "note": "charts are drawing (grok) — killing now throws that work away. "
                    "`newsroom pause` waits for them and keeps it; `--now --force` kills anyway",
        }, indent=2))
        return 1
    if args.now:
        # Safe because every finished step is on disk and resume reloads it — the only loss is
        # the step in flight. No pause file: the process is gone, and a stale request would
        # stop the NEXT run at its first checkpoint.
        from algent_backend.agent_system.runs.control_plane.process_tree import terminate_tree

        killed = terminate_tree(holder.pid) if holder else False
        print(json.dumps({
            "stopped_now": killed, "pid": holder.pid if holder else None,
            "note": ("stopped; `newsroom resume` continues from the last finished step"
                     if killed else "nothing was running"),
        }, indent=2))
        return 0

    request()
    print(json.dumps({
        "pause_requested": True,
        "running": bool(holder),
        "pid": holder.pid if holder else None,
        "charts_drawing": drawing,
        "note": (
            "charts are drawing (grok): the run keeps that work, exiting when they finish "
            "(up to ~10 min) — leave the machine on until it does, or `--now --force` to kill"
            if drawing else
            "the rail stops at its next checkpoint — the end of the step it is in (a research "
            "lane, the draft, the review…) — and exits; `newsroom resume` continues from there"
            if holder else
            "nothing is running; the request will apply to the next run that starts"
        ),
    }, indent=2))
    return 0
