"""
Run control plane — the filesystem surfaces that make runs observable and
drivable from outside the running process.

Every run owns one directory, grouped by agent and counter-prefixed so the most
recent is obvious in a file tree:

    runs_data/<agent_id>/<NNNN>__<run_id>/
      request.json          what was asked (written by start, read by exec)
      state.json            live snapshot: status, pid, timing
      result.json           RunResult + artifact refs at terminal
      done.json             terminal marker (existence = run is over)
      artifacts/            durable outputs written by the agent
      audit/events.jsonl    append-only neutral RunEvent stream (owned trace)
      audit/human/timeline.md   human projection of events (pure renderer)
      audit/error.log       full traceback if the run failed

Plus a per-agent ``_meta.json`` (the monotonic counter) and one cross-run index
(``runs_index.jsonl``) for ledger queries.

These files are the seam that lets any process — a human shell, another agent,
a headless CLI harness — start, watch, and inspect runs. The CLI is only a
reader/trigger over this plane; semantics live in the harness, never in the CLI.
"""

from .layout import (
    RunPaths,
    allocate_run_root,
    find_run_root,
    resolve_or_allocate_run_root,
    runs_data_root,
)
from .recorder import RunRecorder
from .state import RunState, read_state, write_state

__all__ = [
    "RunPaths",
    "RunRecorder",
    "RunState",
    "allocate_run_root",
    "find_run_root",
    "read_state",
    "resolve_or_allocate_run_root",
    "runs_data_root",
    "write_state",
]
