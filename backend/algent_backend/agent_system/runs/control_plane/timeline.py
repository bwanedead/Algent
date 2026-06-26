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
from datetime import datetime

from algent_backend.agent_system.runs.events import (
    AGENT_STEP,
    ARTIFACT_WRITTEN,
    INPUT_PREVIEW,
    MODEL_USAGE,
    NODE_COMPLETED,
    OUTPUT_PREVIEW,
    RAKE_PROGRESS,
    RUN_COMPLETED,
    RUN_ERROR,
    RUN_FAILED,
    RUN_STARTED,
    T0_PROGRESS,
    TOOL_RESULT,
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
    ordered = sorted(events, key=lambda e: e.seq)
    lines: list[str] = [
        "# Run Timeline (Human View)",
        "",
        "Live projection of the run's event stream. Facts only — no",
        "host-authored judgment about what the run means.",
        "",
        *_render_summary(ordered),
        "",
    ]
    turns = _turn_info(ordered)
    for event in ordered:
        lines.extend(_render_event(event, turns))
        lines.append("")
    return "\n".join(lines) + "\n"


_TURN_BAR = "=" * 72


def _turn_info(events: list[RunEvent]) -> dict[int, tuple[int, float | None, str]]:
    """Map each model-step event seq -> (turn number, duration, tools-called).

    A turn is one model decision (an ``agent.step``). Its duration runs to the
    next model step, or to the final event for the last turn.
    """
    steps = [e for e in events if e.type == AGENT_STEP]
    info: dict[int, tuple[int, float | None, str]] = {}
    for i, step in enumerate(steps):
        nxt_ts = steps[i + 1].ts if i + 1 < len(steps) else (events[-1].ts if events else step.ts)
        calls = [c.get("name") for c in (step.payload.get("tool_calls") or []) if c.get("name")]
        summary = "calls " + ", ".join(calls) if calls else "final answer (no tool calls)"
        info[step.seq] = (i + 1, _duration(step.ts, nxt_ts), summary)
    return info


def _render_summary(events: list[RunEvent]) -> list[str]:
    """A small at-a-glance header derived from the event stream."""
    turns = sum(1 for e in events if e.type == AGENT_STEP)
    tool_calls = sum(1 for e in events if e.type == TOOL_RESULT)
    in_tok = sum(int(e.payload.get("input_tokens") or 0) for e in events if e.type == MODEL_USAGE)
    out_tok = sum(int(e.payload.get("output_tokens") or 0) for e in events if e.type == MODEL_USAGE)
    status = next(
        (
            e.payload.get("status", e.type.split(".")[-1])
            for e in reversed(events)
            if e.type in (RUN_COMPLETED, RUN_FAILED, RUN_ERROR)
        ),
        "running",
    )
    duration = _duration(events[0].ts, events[-1].ts) if events else None
    lines = ["## Run Summary", "", f"- status: {status}"]
    if duration is not None:
        lines.append(f"- duration: {duration:.1f}s")
    lines.append(f"- model turns: {turns}   tool calls: {tool_calls}")
    if in_tok or out_tok:
        lines.append(f"- tokens: in={in_tok} out={out_tok}")
    return lines


def _duration(start_iso: str, end_iso: str) -> float | None:
    try:
        return (datetime.fromisoformat(end_iso) - datetime.fromisoformat(start_iso)).total_seconds()
    except ValueError:
        return None


def _render_event(event: RunEvent, turns: dict[int, tuple[int, float | None, str]]) -> list[str]:
    # A model step opens an explicit, countable TURN block (Plattera-style).
    if event.type == AGENT_STEP and event.seq in turns:
        turn_no, duration, calls = turns[event.seq]
        dur = f"{duration:.1f}s" if duration is not None else "?"
        head = f"TURN {turn_no:04d}  |  {calls}  |  duration: {dur}"
        return [_TURN_BAR, head, _TURN_BAR, *_render_agent_step(event)]
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


def _render_agent_step(event: RunEvent) -> list[str]:
    p = event.payload
    calls = p.get("tool_calls") or []
    content = p.get("content")
    lines = [f"- reasoning: {_excerpt(content) if content else '(no text — went straight to tools)'}"]
    if calls:
        lines.append(f"- tools used: {', '.join(c.get('name', '?') for c in calls)}")
        for call in calls:
            lines.append(f"    • {call.get('name', '?')}({_excerpt(call.get('args'))})")
    else:
        lines.append("- tools used: none (final answer)")
    return lines


def _render_t0_progress(event: RunEvent) -> list[str]:
    return [f"- t0: {event.payload.get('message', '')}"]


def _render_rake_progress(event: RunEvent) -> list[str]:
    return [f"- rake: {event.payload.get('message', '')}"]


def _render_output_preview(event: RunEvent) -> list[str]:
    p = event.payload
    lines = [f"- {p.get('title', 'output')}: {p.get('summary', '')}"]
    for line in p.get("items") or []:
        lines.append(f"    {line}")
    if p.get("link"):
        link = str(p["link"]).replace("\\", "/")
        lines.append(f"- full output: [{link}]({link})")
    return lines


def _render_input_preview(event: RunEvent) -> list[str]:
    p = event.payload
    lines = [f"- {p.get('title', 'input')}: {p.get('summary', '')}"]
    for item in p.get("top") or []:
        lines.append(f"    · {item}")
    if p.get("link"):
        # Clickable in most IDEs; also legible as a plain path.
        link = str(p["link"]).replace("\\", "/")
        lines.append(f"- full list: [{link}]({link})")
    return lines


def _render_tool_result(event: RunEvent) -> list[str]:
    p = event.payload
    return [f"- tool: {p.get('tool', '?')}", f"- result: {_excerpt(p.get('content', ''))}"]


def _render_run_error(event: RunEvent) -> list[str]:
    p = event.payload
    lines = [f"- error: {p.get('error', '?')}"]
    tb = p.get("traceback")
    if tb:
        # Render the full traceback (not truncated) — it is the whole point.
        lines.append("- traceback:")
        lines.append("```")
        lines.extend(str(tb).rstrip().splitlines())
        lines.append("```")
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
    RUN_ERROR: _render_run_error,
    AGENT_STEP: _render_agent_step,
    TOOL_RESULT: _render_tool_result,
    INPUT_PREVIEW: _render_input_preview,
    OUTPUT_PREVIEW: _render_output_preview,
    T0_PROGRESS: _render_t0_progress,
    RAKE_PROGRESS: _render_rake_progress,
}


def _excerpt(value: object) -> str:
    text = str(value)
    if len(text) <= EXCERPT_MAX_CHARS:
        return text
    return text[:EXCERPT_MAX_CHARS] + f" ... [truncated, {len(text)} chars total]"
