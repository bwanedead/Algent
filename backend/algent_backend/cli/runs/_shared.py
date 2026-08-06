"""
Shared CLI mechanics: JSON output, input parsing, process liveness.

Mechanics only — nothing here may interpret run semantics.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any

# Liveness + tree-kill live in the control plane; CLI keeps the established names.
from algent_backend.agent_system.runs.control_plane.liveness import process_alive as pid_alive
from algent_backend.agent_system.runs.control_plane.process_tree import (
    terminate_tree as terminate_process,
)


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
