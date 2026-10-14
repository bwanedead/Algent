"""
Redo ONLY the visuals step of a saved day: no writer call, no research, no change to any text.

The daily plans and draws visuals as its last additive step (``visuals.attach``). When that step fails for reasons
that have nothing to do with the day's content (a harness that could not start, a hosting hiccup) the record is fine
and only the pictures are missing; rebuying the whole day to get them would be absurd. This reads the saved record,
runs the same ``attach`` over its sections (one small planning call, then the harness per kept visual), and writes
the record back with the new ``section["visuals"]`` and ``visuals_run``.

Prior visuals are kept by default (drawn work is never redone: ``attach`` reuses them and plans nothing); ``fresh``
drops them first, which is how a day whose visuals were bad gets a new plan.
"""

from __future__ import annotations

import json
from collections.abc import Callable
from typing import Any

from . import daily, desk, render, visuals
from .brief import safe_name


def redo(ctx: Any, model_spec: Any, domain: str, as_of: str, *, fresh: bool = False, out: Any = None,
         ask: Callable[[Any, str, str], Any] | None = None, **attach_kwargs: Any) -> dict:
    """Plan/draw/attach ``as_of``'s visuals over its saved record. ``attach_kwargs`` (``ready``, ``runner``,
    ``uploader``) are the seams ``visuals.attach`` exposes. Returns ``{"report", "path", "visuals_run",
    "produced"}`` or ``{"error"}``."""
    path = daily.daily_dir(domain) / f"{as_of}.json"
    if not path.is_file():
        return {"error": f"no daily record at {path}"}
    record = json.loads(path.read_text(encoding="utf-8"))
    sections = record.get("theaters") or []
    if not sections:
        return {"error": f"{as_of} has no theater sections to draw visuals for"}
    if fresh:
        for s in sections:
            s.pop("visuals", None)
    had = sum(len(s.get("visuals") or []) for s in sections)
    report = visuals.attach(
        sections, ctx=ctx, domain=domain, as_of=as_of, prior=None if fresh else record,
        ask=ask or (lambda schema, role, task: daily._ask(ctx, None, model_spec, schema, role, task)),
        **attach_kwargs)
    now = sum(len(s.get("visuals") or []) for s in sections)
    if report is not None:
        record["visuals_run"] = report
    desk._write(path, record)
    result: dict[str, Any] = {"report": record, "path": str(path), "visuals_run": report, "produced": now - had}
    if out is not None:
        html = out / f"daily_{safe_name(domain)}.html"
        html.write_text(render.render_daily(record), encoding="utf-8")
        result["html"] = str(html)
    return result
