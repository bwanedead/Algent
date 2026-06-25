"""
Per-turn audit traces — ``audit/turns/turn_NNNN.json``.

The machine event stream (``events.jsonl``) is flat; the human timeline is prose.
This is the third audit surface: one JSON file per model turn, so a run can be
reviewed turn-by-turn — what the model said, what tools it called with which args,
and what each tool returned. The sequence of turn files is the full input→output
trace of the run (each turn's output is the next turn's input).

A pure renderer over the event stream, re-written after each event like the
timeline, and best-effort: an audit-write hiccup must never break a live run.
"""

from __future__ import annotations

import json
import logging

from algent_backend.agent_system.runs.events import AGENT_STEP, TOOL_RESULT, RunEvent

from .fsio import atomic_write_text
from .layout import RunPaths

_LOG = logging.getLogger(__name__)


def write_turn_traces(paths: RunPaths, events: list[RunEvent]) -> None:
    """Render and write the per-turn JSON traces. Best-effort by design."""
    try:
        turns = build_turns(sorted(events, key=lambda e: e.seq))
        if not turns:
            return
        paths.audit_dir.mkdir(parents=True, exist_ok=True)
        for turn in turns:
            atomic_write_text(
                paths.turn_file(turn["turn"]),
                json.dumps(turn, indent=2, default=str, ensure_ascii=False),
            )
    except Exception:
        _LOG.warning("turn-trace write failed; audit/turns may be stale", exc_info=True)


def build_turns(events: list[RunEvent]) -> list[dict]:
    """Group the event stream into per-turn records.

    A turn opens on a model step (``agent.step``) and absorbs the tool results
    that follow it until the next model step.
    """
    turns: list[dict] = []
    current: dict | None = None
    for event in events:
        if event.type == AGENT_STEP:
            current = {
                "turn": len(turns) + 1,
                "ts": event.ts,
                "model_output": {
                    "content": event.payload.get("content", ""),
                    "tool_calls": event.payload.get("tool_calls", []),
                },
                "tool_results": [],
            }
            turns.append(current)
        elif event.type == TOOL_RESULT and current is not None:
            current["tool_results"].append(
                {"tool": event.payload.get("tool"), "content": event.payload.get("content", "")}
            )
    return turns
