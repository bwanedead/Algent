"""
Publish conflict events to the site database (migration 014: ``conflict_events``, anon read-only).

Same contract as ``sanctions/publish``: never raises, idempotent (``on conflict do nothing``), a no-op without ``DATABASE_URL``. A watermark per
event-date shard (``published.json``) lets each run send only what is new; the most-reported ``PUBLISH_PER_DAY`` events of a day are sent (the local
record keeps all). ``full=True`` resends the recent window.
"""

from __future__ import annotations

import json
from collections.abc import Callable
from datetime import date, timedelta
from typing import Any

from algent_backend.publishing.published_db import _run

from . import flags, store
from .contracts import ConflictEvent

_COLS = ("id", "source", "on_date", "observed_at", "type", "code", "lat", "lon", "place", "country", "actor1", "actor2", "fatalities", "articles",
         "title", "urls", "coding", "confidence", "basis", "coverage_note", "assets")
_ROW = (f"insert into conflict_events ({', '.join(_COLS)}) values ({', '.join('%s::jsonb' if c == 'assets' else '%s' for c in _COLS)}) "
        "on conflict (id) do nothing")


def row(e: ConflictEvent) -> tuple:
    return (e.id, e.source, e.date, e.observed_at, e.type, e.code, e.lat, e.lon, e.place, e.country, e.actor1, e.actor2, e.fatalities, e.articles,
            e.title, e.urls, e.coding, e.confidence, e.basis, e.coverage_note, json.dumps([a.model_dump() for a in e.assets]))


def pending(*, full: bool = False, today: date | None = None) -> tuple[list[ConflictEvent], dict[str, dict[str, int]]]:
    """(events to send, the watermarks to save once they are committed)."""
    today = today or date.today()
    floor = (today - timedelta(days=flags.PUBLISH_DAYS)).isoformat()
    marks = store.published()
    send: list[ConflictEvent] = []
    for day in store.shard_days():
        if day < floor:
            continue
        mark = {"lines": 0, "sent": 0} if full else marks.get(day, {"lines": 0, "sent": 0})
        rows = store.lines_after(day, mark["lines"])
        total = mark["lines"] + len(rows)
        room = max(0, flags.PUBLISH_PER_DAY - mark["sent"])
        rows = sorted(rows, key=lambda e: -e.articles)[:room]
        send += rows
        marks[day] = {"lines": total, "sent": mark["sent"] + len(rows)}
    return send, marks


def publish(*, full: bool = False, today: date | None = None, connect: Callable[[], Any] | None = None) -> dict[str, Any]:
    send, marks = pending(full=full, today=today)
    if not send:
        store.save_published(marks)
        return {"db": True, "events": 0, "note": "nothing new"}

    def work(conn: Any) -> dict:
        with conn.cursor() as cur:
            cur.executemany(_ROW, [row(e) for e in send])
        return {"events": len(send)}

    result = _run(work, connect)
    if result.get("db"):
        store.save_published(marks)                         # only after the commit: a failed publish is retried whole
    return result
