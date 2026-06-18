"""
``stop`` — terminate a run and mark it stopped.

The operator's kill switch: for a run that has gone bad, is spinning, or is
costing more than it is worth. It hard-terminates the run's process (and its
child tree), then writes the terminal control-plane surfaces — a stop event, a
``stopped`` state, a ledger row, and ``done.json`` — so any watcher sees the run
end cleanly.

A run is a single blocking model loop with no cooperative checkpoint, so this is
a hard terminate, not a graceful pause. Cooperative pause/resume can come when
agents have safe interruption points. The stop command runs in the operator's
shell (a different process than the run), so it writes the run's files directly.
"""

from __future__ import annotations

import argparse
from datetime import UTC, datetime

from algent_backend.agent_system.runs import events as ev
from algent_backend.agent_system.runs.control_plane.events_log import RunEventLog, read_events
from algent_backend.agent_system.runs.control_plane.fsio import write_json_file
from algent_backend.agent_system.runs.control_plane.layout import RunPaths, find_run_root
from algent_backend.agent_system.runs.control_plane.ledger import LedgerEntry, RunLedger
from algent_backend.agent_system.runs.control_plane.state import read_state, write_state
from algent_backend.agent_system.runs.control_plane.timeline import write_timeline

from ._shared import print_json, terminate_process

_TERMINAL = {"completed", "failed", "stopped"}


def add_parser(subparsers: argparse._SubParsersAction) -> None:
    parser = subparsers.add_parser("stop", help="terminate a run and mark it stopped")
    parser.add_argument("--run-id", required=True)
    parser.add_argument("--reason", default="stopped by operator")
    parser.set_defaults(handler=run)


def run(args: argparse.Namespace) -> int:
    root = find_run_root(args.run_id)
    if root is None:
        print_json({"error": f"unknown run '{args.run_id}'"})
        return 1
    paths = RunPaths(root)

    state = read_state(paths)
    if paths.done_file.exists() or state.status in _TERMINAL:
        print_json({"run_id": args.run_id, "status": state.status, "note": "already terminal"})
        return 0

    killed = terminate_process(state.pid)
    now = datetime.now(UTC).isoformat()

    # The run's process is gone; we now own its files. Continue the event sequence
    # after the existing events, then re-render the (full) timeline.
    prior = read_events(paths)
    start_seq = max((e.seq for e in prior), default=0)
    log = RunEventLog(paths, args.run_id, start_seq=start_seq)
    log.append(ev.RUN_STOPPED, {"reason": args.reason, "killed_process": killed})
    write_timeline(paths, prior + log.appended)

    write_state(
        paths,
        state.model_copy(update={"status": "stopped", "updated_at": now, "error": args.reason}),
    )

    RunLedger().append(
        LedgerEntry(
            run_id=args.run_id,
            agent_id=state.agent_id,
            runtime=state.runtime,
            status="stopped",
            created_at=state.created_at,
            finished_at=now,
            error=args.reason,
        )
    )
    # done.json last: its existence is the terminal signal watchers poll for.
    write_json_file(paths.done_file, {"run_id": args.run_id, "status": "stopped"})

    print_json(
        {
            "run_id": args.run_id,
            "status": "stopped",
            "killed_process": killed,
            "reason": args.reason,
        }
    )
    return 0
