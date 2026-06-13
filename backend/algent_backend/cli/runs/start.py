"""
``start`` — launch a run (background child by default, ``--foreground`` inline).

The parent allocates the run id, writes ``request.json`` and a ``queued``
state snapshot, then either spawns a detached ``exec`` child or executes
inline. Watchers can attach to the run id the moment this command returns.
"""

from __future__ import annotations

import argparse
import subprocess
import sys
from datetime import UTC, datetime
from uuid import uuid4

from algent_backend.agent_system.runs.control_plane.fsio import write_json_file
from algent_backend.agent_system.runs.control_plane.layout import run_paths
from algent_backend.agent_system.runs.control_plane.state import RunState, write_state
from algent_backend.agent_system.runs.models import RunRequest

from ._shared import parse_input_arg, print_json


def add_parser(subparsers: argparse._SubParsersAction) -> None:
    parser = subparsers.add_parser("start", help="start a run")
    parser.add_argument("agent_id")
    parser.add_argument("--input", help='run input as a JSON object, e.g. \'{"topic": "..."}\'')
    parser.add_argument("--topic", help="shortcut for --input '{\"topic\": ...}'")
    parser.add_argument("--runtime", default="langgraph")
    parser.add_argument("--max-turns", type=int, default=None)
    parser.add_argument(
        "--foreground",
        action="store_true",
        help="execute in this process instead of spawning a background child",
    )
    parser.set_defaults(handler=run)


def run(args: argparse.Namespace) -> int:
    run_id = str(uuid4())
    request = RunRequest(
        agent_id=args.agent_id,
        input=parse_input_arg(args.input, args.topic),
        runtime=args.runtime,
        run_id=run_id,
        max_turns=args.max_turns,
    )

    paths = run_paths(run_id)
    write_json_file(paths.request_file, request.model_dump())
    now = datetime.now(UTC).isoformat()
    write_state(
        paths,
        RunState(
            run_id=run_id,
            agent_id=request.agent_id,
            runtime=request.runtime,
            status="queued",
            created_at=now,
            updated_at=now,
            input=request.input,
            max_turns=request.max_turns,
        ),
    )

    if args.foreground:
        from . import exec_run

        exit_code = exec_run.execute(run_id)
        print_json({"run_id": run_id, "mode": "foreground", "exit_code": exit_code})
        return exit_code

    _spawn_detached(run_id)
    print_json({"run_id": run_id, "mode": "background"})
    return 0


def _spawn_detached(run_id: str) -> None:
    paths = run_paths(run_id)
    command = [sys.executable, "-m", "algent_backend.cli.runs", "exec", "--run-id", run_id]

    stdout = paths.child_stdout_file.open("ab")
    stderr = paths.child_stderr_file.open("ab")
    kwargs: dict = {"stdout": stdout, "stderr": stderr, "stdin": subprocess.DEVNULL}
    if sys.platform == "win32":
        kwargs["creationflags"] = subprocess.DETACHED_PROCESS | subprocess.CREATE_NEW_PROCESS_GROUP
    else:
        kwargs["start_new_session"] = True
    subprocess.Popen(command, **kwargs)
    stdout.close()
    stderr.close()
