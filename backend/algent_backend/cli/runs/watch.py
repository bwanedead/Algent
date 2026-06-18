"""
``watch`` — blocking single-event poll on one run.

Returns exactly one JSON event, then exits:

- ``{"event": "loop_done", ...}``  the run reached a terminal state
- ``{"event": "timeout", ...}``    nothing happened inside this watch window
- ``{"event": "error", ...}``      run unknown, or its process died mid-run

Callers (humans or agents) loop: watch -> react -> watch again. HITL events
join this surface in a later slice; the event shape is already a tagged union
so consumers tolerate new event kinds.
"""

from __future__ import annotations

import argparse
import json
import time

from algent_backend.agent_system.runs.control_plane.layout import RunPaths, find_run_root
from algent_backend.agent_system.runs.control_plane.state import read_state

from ._shared import pid_alive, print_json


def add_parser(subparsers: argparse._SubParsersAction) -> None:
    parser = subparsers.add_parser("watch", help="block until the run's next event")
    parser.add_argument("--run-id", required=True)
    parser.add_argument("--timeout", type=float, default=600.0, help="seconds")
    parser.add_argument("--poll-interval", type=float, default=2.0, help="seconds")
    parser.set_defaults(handler=run)


def run(args: argparse.Namespace) -> int:
    root = find_run_root(args.run_id)
    if root is None:
        print_json({"event": "error", "reason": f"unknown run '{args.run_id}'"})
        return 1
    paths = RunPaths(root)
    deadline = time.monotonic() + args.timeout

    while True:
        if paths.done_file.exists():
            done = json.loads(paths.done_file.read_text(encoding="utf-8"))
            print_json({"event": "loop_done", **done})
            return 0

        if not paths.state_file.exists():
            print_json({"event": "error", "reason": f"unknown run '{args.run_id}'"})
            return 1

        state = read_state(paths)
        if state.status == "running" and not pid_alive(state.pid):
            print_json(
                {
                    "event": "error",
                    "reason": "process_dead",
                    "run_id": args.run_id,
                    "pid": state.pid,
                }
            )
            return 1

        if time.monotonic() >= deadline:
            print_json({"event": "timeout", "run_id": args.run_id, "status": state.status})
            return 0

        time.sleep(args.poll_interval)
