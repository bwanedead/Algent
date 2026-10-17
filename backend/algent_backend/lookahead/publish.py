"""
Publish the calendar to the site database (migration 012: ``calendar_items``, anon read-only).

Never raises, idempotent, a no-op without ``DATABASE_URL`` (the contract of ``publishing/published_db``). The calendar is a few
hundred rows, so every run upserts the items from a week ago onward (including withdrawn ones, which flip ``active`` off); a
row whose content is unchanged is not rewritten.
"""

from __future__ import annotations

from collections.abc import Callable
from datetime import date, timedelta
from typing import Any

from algent_backend.publishing.published_db import _run

from . import store
from .contracts import CalendarItem

KEEP_DAYS_BACK = 7
_ROW = """
insert into calendar_items (id, on_date, end_date, title, kind, countries, theaters, source, source_url, confidence, provenance, via, active)
values (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
on conflict (id) do update
   set on_date = excluded.on_date, end_date = excluded.end_date, title = excluded.title, countries = excluded.countries,
       theaters = excluded.theaters, source_url = excluded.source_url, confidence = excluded.confidence, active = excluded.active,
       updated_at = now()
 where (calendar_items.on_date, calendar_items.end_date, calendar_items.title, calendar_items.countries, calendar_items.theaters,
        calendar_items.source_url, calendar_items.confidence, calendar_items.active)
       is distinct from (excluded.on_date, excluded.end_date, excluded.title, excluded.countries, excluded.theaters,
                         excluded.source_url, excluded.confidence, excluded.active)
"""


def row(i: CalendarItem) -> tuple:
    return (i.id, i.date, i.end_date or None, i.title, i.kind, i.countries, i.theaters, i.source, i.source_url, i.confidence,
            i.provenance, i.via, i.active)


def publish(*, today: date | None = None, connect: Callable[[], Any] | None = None) -> dict[str, Any]:
    horizon = ((today or date.today()) - timedelta(days=KEEP_DAYS_BACK)).isoformat()
    items = [i for i in store.current().values() if (i.end_date or i.date) >= horizon]
    if not items:
        return {"db": True, "items": 0, "note": "nothing to send"}

    def work(conn: Any) -> dict:
        with conn.cursor() as cur:
            cur.executemany(_ROW, [row(i) for i in items])
        return {"items": len(items)}

    return _run(work, connect)
