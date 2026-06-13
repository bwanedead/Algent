"""
Run control plane — the filesystem surfaces that make runs observable and
drivable from outside the running process.

Every run owns one directory under the runs-data root:

    runs_data/<run_id>/
      request.json     what was asked (written by start, read by exec)
      state.json       live snapshot: status, pid, timing
      events.jsonl     append-only neutral RunEvent stream (canonical owned trace)
      timeline.md      human projection of events (pure renderer, no judgments)
      result.json      RunResult + artifact refs at terminal
      done.json        terminal marker (existence = run is over)
      artifacts/       durable outputs written by the agent

Plus one cross-run index (``runs_index.jsonl``) for ledger queries.

These files are the seam that lets any process — a human shell, another agent,
a headless CLI harness — start, watch, and inspect runs. The CLI is only a
reader/trigger over this plane; semantics live in the harness, never in the CLI.
"""

from .layout import RunPaths, run_paths, runs_data_root
from .recorder import RunRecorder
from .state import RunState, read_state, write_state

__all__ = [
    "RunPaths",
    "RunRecorder",
    "RunState",
    "read_state",
    "run_paths",
    "runs_data_root",
    "write_state",
]
