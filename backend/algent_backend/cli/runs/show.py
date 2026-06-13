"""``show`` — full detail for one run: state, result, artifacts, file locations."""

from __future__ import annotations

import argparse
import json

from algent_backend.agent_system.runs.control_plane.events_log import read_events
from algent_backend.agent_system.runs.control_plane.layout import run_paths
from algent_backend.agent_system.runs.control_plane.state import read_state

from ._shared import print_json


def add_parser(subparsers: argparse._SubParsersAction) -> None:
    parser = subparsers.add_parser("show", help="show one run in full")
    parser.add_argument("--run-id", required=True)
    parser.set_defaults(handler=run)


def run(args: argparse.Namespace) -> int:
    paths = run_paths(args.run_id)
    if not paths.state_file.exists():
        print_json({"error": f"unknown run '{args.run_id}'"})
        return 1

    result = None
    if paths.result_file.exists():
        result = json.loads(paths.result_file.read_text(encoding="utf-8"))

    print_json(
        {
            "state": read_state(paths).model_dump(),
            "result": result,
            "event_count": len(read_events(paths)),
            "paths": {
                "root": str(paths.root),
                "timeline": str(paths.timeline_file),
                "events": str(paths.events_file),
                "artifacts": str(paths.artifacts_dir),
            },
        }
    )
    return 0
