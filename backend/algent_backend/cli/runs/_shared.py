"""
Shared CLI mechanics: JSON output, input parsing, process liveness.

Mechanics only — nothing here may interpret run semantics.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any

from algent_backend.agent_system.runs.control_plane.liveness import process_alive


def print_json(payload: Any) -> None:
    """Print the command's single JSON document."""
    # Windows consoles default to cp1252 and crash on non-ASCII (e.g. world-news
    # titles). Force UTF-8, degrading un-encodable chars rather than raising.
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    json.dump(payload, sys.stdout, ensure_ascii=False, indent=2, default=str)
    sys.stdout.write("\n")


def parse_input_arg(
    input_json: str | None,
    topic: str | None,
    goal: str | None = None,
    input_file: str | None = None,
    input_key: str | None = None,
) -> dict[str, Any]:
    """Build the run input — the graph's initial state — from the input flags.

    The run input IS the graph's initial state, so feeding a saved artifact lets a
    stage run in ISOLATION on supplied upstream output instead of producing it:
      --input-file FILE              load a JSON object as the whole input dict
      --input-file FILE --input-key K  mount the file's JSON under state key K, i.e.
                                       {K: <file>} (e.g. K=pool feeds synthesis a
                                       saved t0 pool; K=portfolio feeds the router)
    ``--input`` / ``--topic`` / ``--goal`` then merge on top.
    """
    payload: dict[str, Any] = {}
    if input_file:
        loaded = json.loads(Path(input_file).read_text(encoding="utf-8"))
        if input_key:
            payload[input_key] = loaded
        elif isinstance(loaded, dict):
            payload.update(loaded)
        else:
            raise ValueError("--input-file must contain a JSON object unless --input-key is given")
    if input_json:
        parsed = json.loads(input_json)
        if not isinstance(parsed, dict):
            raise ValueError("--input must be a JSON object")
        payload.update(parsed)
    if topic is not None:
        payload["topic"] = topic
    if goal is not None:
        payload["goal"] = goal
    return payload


# One liveness implementation, owned by the control plane (state.py needs it to reconcile a run
# whose process vanished). Re-exported here so the CLI keeps its established name.
pid_alive = process_alive


def terminate_process(pid: int | None) -> bool:
    """Best-effort hard-terminate a run's process (and its child tree).

    A run is a single blocking model loop with no cooperative checkpoint, so the
    operator stop is a hard kill, not a graceful pause. Returns whether a live
    process was signalled.
    """
    if pid is None or not pid_alive(pid):
        return False
    try:
        if sys.platform == "win32":
            import subprocess

            # /T kills the child tree, /F forces it.
            subprocess.run(
                ["taskkill", "/F", "/T", "/PID", str(pid)],
                capture_output=True,
                check=False,
            )
        else:
            import os
            import signal

            try:
                os.killpg(pid, signal.SIGTERM)  # child is its own session/group leader
            except (ProcessLookupError, PermissionError):
                os.kill(pid, signal.SIGTERM)
        return True
    except Exception:
        return False


