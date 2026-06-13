"""
Human timeline — ``timeline.md``, the readable live projection of a run.

A pure renderer over the run's event stream, re-rendered after every event so
the file stays current mid-run. Adapted from Plattera's human-timeline rules:

- facts and model-authored text only — the renderer never authors judgments
  (no "stuck", "spinning", verdicts); the human decides what the run means
- nothing is filtered for relevance; long fields get a visible truncation marker
- atomic writes, and rendering is best-effort: a timeline failure must never
  block or fail a live run

What counts as "the details that matter" evolves by editing this one renderer —
the event contract never changes for presentation reasons.
"""

from __future__ import annotations

import logging

from algent_backend.agent_system.runs.events import (
    ARTIFACT_WRITTEN,
    MODEL_USAGE,
    NODE_COMPLETED,
    RUN_COMPLETED,
    RUN_FAILED,
    RUN_STARTED,
    RunEvent,
)

from .fsio import atomic_write_text
from .layout import RunPaths

_LOG = logging.getLogger(__name__)

EXCERPT_MAX_CHARS = 2000
_BAR = "-" * 72


def write_timeline(paths: RunPaths, events: list[RunEvent]) -> None:
    """Render and atomically write ``timeline.md``. Best-effort by design."""
    try:
        atomic_write_text(paths.timeline_file, render_timeline(events))
    except Exception:
        _LOG.warning("timeline write failed; timeline.md may be stale", exc_info=True)


def render_timeline(events: list[RunEvent]) -> str:
    lines: list[str] = [
        "# Run Timeline (Human View)",
        "",
        "Live projection of the run's event stream. Facts only — no",
        "host-authored judgment about what the run means.",
        "",
    ]
    for event in sorted(events, key=lambda e: e.seq):
        lines.extend(_render_event(event))
        lines.append("")
    return "\n".join(lines) + "\n"


def _render_event(event: RunEvent) -> list[str]:
    head = f"## [{event.seq:04d}] {event.type}  ({event.ts})"
    body = _RENDERERS.get(event.type, _render_generic)(event)
    return [_BAR, head, *body]


def _render_run_started(event: RunEvent) -> list[str]:
    p = event.payload
    lines = [f"- agent: {p.get('agent_id', '?')}  runtime: {p.get('runtime', '?')}"]
    if p.get("input") is not None:
        lines.append(f"- input: {_excerpt(p['input'])}")
    if p.get("max_turns") is not None:
        lines.append(f"- max_turns: {p['max_turns']}")
    return lines


def _render_node_completed(event: RunEvent) -> list[str]:
    p = event.payload
    lines = [f"- node: {p.get('node', '?')}"]
    update = p.get("update")
    if update is not None:
        lines.append(f"- update: {_excerpt(update)}")
    return lines


def _render_model_usage(event: RunEvent) -> list[str]:
    p = event.payload
    return [
        f"- model: {p.get('model', '?')}  "
        f"input_tokens: {p.get('input_tokens', '?')}  "
        f"output_tokens: {p.get('output_tokens', '?')}"
    ]


def _render_artifact_written(event: RunEvent) -> list[str]:
    p = event.payload
    return [
        f"- artifact: {p.get('name', '?')}  kind: {p.get('kind', '?')}  "
        f"size: {p.get('size_bytes', '?')} bytes",
        f"- path: artifacts/{p.get('relative_path', '?')}",
    ]


def _render_run_terminal(event: RunEvent) -> list[str]:
    p = event.payload
    lines = [f"- status: {p.get('status', '?')}"]
    if p.get("error"):
        lines.append(f"- error: {_excerpt(p['error'])}")
    if p.get("output") is not None:
        lines.append(f"- output: {_excerpt(p['output'])}")
    return lines


def _render_generic(event: RunEvent) -> list[str]:
    if not event.payload:
        return ["- (no payload)"]
    return [f"- {key}: {_excerpt(value)}" for key, value in event.payload.items()]


_RENDERERS = {
    RUN_STARTED: _render_run_started,
    NODE_COMPLETED: _render_node_completed,
    MODEL_USAGE: _render_model_usage,
    ARTIFACT_WRITTEN: _render_artifact_written,
    RUN_COMPLETED: _render_run_terminal,
    RUN_FAILED: _render_run_terminal,
}


def _excerpt(value: object) -> str:
    text = str(value)
    if len(text) <= EXCERPT_MAX_CHARS:
        return text
    return text[:EXCERPT_MAX_CHARS] + f" ... [truncated, {len(text)} chars total]"
