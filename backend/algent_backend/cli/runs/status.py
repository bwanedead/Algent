"""
``status`` — current snapshot of one run.

Reads run files; adds only mechanical observations (done marker present,
process liveness). No interpretation.
"""

from __future__ import annotations

import argparse

from algent_backend.agent_system.runs.control_plane.layout import RunPaths, find_run_root
from algent_backend.agent_system.runs.control_plane.state import read_state

from ._shared import pid_alive, print_json


def add_parser(subparsers: argparse._SubParsersAction) -> None:
    parser = subparsers.add_parser("status", help="show one run's current state")
    parser.add_argument("--run-id", required=True)
    parser.set_defaults(handler=run)


def run(args: argparse.Namespace) -> int:
    root = find_run_root(args.run_id)
    if root is None:
        print_json({"error": f"unknown run '{args.run_id}'"})
        return 1
    paths = RunPaths(root)

    state = read_state(paths)
    print_json(
        {
            **state.model_dump(),
            "done": paths.done_file.exists(),
            "process_alive": pid_alive(state.pid) if state.status == "running" else None,
        }
    )
    return 0
