"""
Publish the calendar to the site: ``calendar/next.json`` (every active item in the window, merged across sources and ranked) and
``calendar/country/<ISO>.json`` (that country's rows, for its actor page and the country filter). The object store skips a document
whose content hash is unchanged, so a daily run with nothing new writes nothing; documents are small (budget in the registry).

The window is 14 days back (context: what just happened or was just decided) and 180 ahead (``sources.HORIZON_DAYS``). The legacy
Postgres table (migration 012, anon read-only) stays behind its flag and receives only the original seven kinds its check allows.
"""

from __future__ import annotations

from collections.abc import Callable
from datetime import date, timedelta
from typing import Any

from algent_backend.publishing import published_db, site_data
from algent_backend.publishing.published_db import _run

from . import merge, rank, store
from .contracts import CalendarItem
from .sources import HORIZON_DAYS, LOOKBACK_DAYS

KEEP_DAYS_BACK = LOOKBACK_DAYS
AHEAD_DAYS = HORIZON_DAYS
LEGACY_KINDS = ("election", "central_bank", "summit", "security_council", "opec", "deadline", "vote")
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


#: The table's columns first (rows are ``CalendarRow`` in lib/calendar-shared.ts), then the additive ones.
COLUMNS = ("id", "on_date", "end_date", "title", "kind", "countries", "theaters", "source", "source_url", "confidence", "provenance", "via", "active")


def as_row(i: CalendarItem) -> dict[str, Any]:
    out = dict(zip(COLUMNS, row(i)))
    out.update(situations=i.situations, grade=i.grade, topic=i.topic, importance=i.importance,
               sources=i.sources or [{"source": i.source, "url": i.source_url}])
    return out


def window_items(today: date, hot: set[str] | None = None) -> list[CalendarItem]:
    """Active store items in the window, merged across sources, each with its importance, soonest first."""
    lo, hi = (today - timedelta(days=KEEP_DAYS_BACK)).isoformat(), (today + timedelta(days=AHEAD_DAYS)).isoformat()
    items = [i for i in store.current().values() if i.active and (i.end_date or i.date) >= lo and i.date <= hi]
    hot = rank.hot_theaters() if hot is None else hot
    return [i.model_copy(update={"importance": rank.importance(i, hot)}) for i in merge.merge(items)]


def documents(today: date | None = None, hot: set[str] | None = None) -> dict[str, Any]:
    """``calendar/next.json`` and one ``calendar/country/<ISO>.json`` per country with an item. Market resolution dates (hundreds of them) go to
    their own ``calendar/markets.json`` for the Predictions page only: in the general calendar, the Daily strips and Home they drowned the
    events a reader actually watches (operator, 2026-10-25)."""
    every = sorted((as_row(i) for i in window_items(today or date.today(), hot)), key=lambda r: (r["on_date"], -r["importance"], r["id"]))
    rows = [r for r in every if r["kind"] != "market_resolves"]
    docs: dict[str, Any] = {"calendar/next.json": {"items": rows}, "calendar/markets.json": {"items": [r for r in every if r["kind"] == "market_resolves"]}}
    by_country: dict[str, list[dict[str, Any]]] = {}
    for r in rows:
        for c in r["countries"]:
            if len(c) == 2:
                by_country.setdefault(c.upper(), []).append(r)
    docs.update({f"calendar/country/{c}.json": {"items": rs} for c, rs in sorted(by_country.items())})
    return docs


def publish(*, today: date | None = None, connect: Callable[[], Any] | None = None) -> dict[str, Any]:
    files = site_data.publish_built(lambda: documents(today))
    if published_db.files_only(connect):
        return files
    out = _publish_table(today=today, connect=connect)
    if files.get("ok"):
        out["files"] = files
    return out


def _publish_table(*, today: date | None = None, connect: Callable[[], Any] | None = None) -> dict[str, Any]:
    horizon = ((today or date.today()) - timedelta(days=KEEP_DAYS_BACK)).isoformat()
    items = [i for i in store.current().values() if (i.end_date or i.date) >= horizon and i.kind in LEGACY_KINDS]
    if not items:
        return {"db": True, "items": 0, "note": "nothing to send"}

    def work(conn: Any) -> dict:
        with conn.cursor() as cur:
            cur.executemany(_ROW, [row(i) for i in items])
        return {"items": len(items)}

    return _run(work, connect)
