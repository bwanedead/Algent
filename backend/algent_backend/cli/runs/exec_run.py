"""
``exec`` — execute a previously started run in this process.

Internal command: ``start`` spawns it (or calls it inline for ``--foreground``).
Reads ``request.json`` from the run directory and hands it to ``RunService``,
which owns all recording. The CLI adds nothing semantic.
"""

from __future__ import annotations

import argparse

from algent_backend.agent_system.runs.control_plane.layout import run_paths
from algent_backend.agent_system.runs.models import RunRequest

from ._shared import print_json


def add_parser(subparsers: argparse._SubParsersAction) -> None:
    parser = subparsers.add_parser("exec", help="execute a started run (internal)")
    parser.add_argument("--run-id", required=True)
    parser.set_defaults(handler=run)


def run(args: argparse.Namespace) -> int:
    return execute(args.run_id, emit_json=True)


def execute(run_id: str, emit_json: bool = False) -> int:
    paths = run_paths(run_id)
    request = RunRequest.model_validate_json(paths.request_file.read_text(encoding="utf-8"))

    # Imported here so `--help`/status paths stay light: building the default
    # registries pulls in agents and the runtime rail.
    from algent_backend.agent_system.runs.service import RunService

    result = RunService().run(request)
    if emit_json:
        print_json(result.model_dump())
    return 0 if result.status == "completed" else 1
