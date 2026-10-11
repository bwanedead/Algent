"""
Publish live rows for the site: ``live_events`` (current events per feed) and ``live_stats`` (daily series values).

Same contract as ``publishing/published_db``: never raises, idempotent, a no-op without ``DATABASE_URL`` (or with
``ALGENT_DB_PUBLISH=0``). Events a feed no longer reports are marked ``active = false`` (kept as history, hidden
from the public view). Stats: the completed days of the last ``PUBLISH_STATS_DAYS`` plus the running (partial) day.
"""

from __future__ import annotations

import json
from datetime import date, timedelta
from typing import Any, Callable

from algent_backend.instruments import store as istore
from algent_backend.instruments.catalog import CATALOG
from algent_backend.instruments.contracts import period_date
from algent_backend.publishing.published_db import _run

from . import flags, store
from .contracts import LiveEvent
from .regions import GATES, REGIONS, FIRE_BOXES

_EVENT = """
insert into live_events (id, feed, kind, title, detail, lat, lon, countries, severity, starts_at, ends_at,
                         source_url, source, tags, data, active)
values (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s::jsonb, true)
on conflict (id) do update
   set title = excluded.title, detail = excluded.detail, lat = excluded.lat, lon = excluded.lon,
       countries = excluded.countries, severity = excluded.severity, starts_at = excluded.starts_at,
       ends_at = excluded.ends_at, source_url = excluded.source_url, tags = excluded.tags, data = excluded.data,
       active = true, updated_at = now()
"""
_RETIRE = "update live_events set active = false, updated_at = now() where feed = %s and active and not (id = any(%s))"
_STAT = """
insert into live_stats (series_id, period, value, partial, name, unit, kind, region, lat, lon, source_url)
values (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
on conflict (series_id, period) do update
   set value = excluded.value, partial = excluded.partial, name = excluded.name, updated_at = now()
 where live_stats.value is distinct from excluded.value or live_stats.partial is distinct from excluded.partial
"""


def _where() -> dict[str, tuple[str, str, float, float]]:
    """series_id -> (kind, region slug, lat, lon) for the series we publish."""
    from algent_backend.instruments.live_series import ais_ids, fire_id, mil_ids

    out: dict[str, tuple[str, str, float, float]] = {}
    for g in GATES:
        lat, lon = (g.a[0] + g.b[0]) / 2, (g.a[1] + g.b[1]) / 2
        for sid, kind in zip(ais_ids(g.slug), ("ships", "tankers")):
            out[sid] = (kind, g.slug, lat, lon)
    for r in REGIONS:
        lat, lon = (r.box[0] + r.box[2]) / 2, (r.box[1] + r.box[3]) / 2
        for sid, kind in zip(mil_ids(r.slug), ("aircraft", "aircraft_support")):
            out[sid] = (kind, r.slug, lat, lon)
    for b in FIRE_BOXES:
        out[fire_id(b.slug)] = ("fires", b.slug, (b.box[0] + b.box[2]) / 2, (b.box[1] + b.box[3]) / 2)
    return out


def stat_rows(today: date) -> list[tuple]:
    where, running, rows = _where(), store.running(), []
    horizon = today - timedelta(days=flags.PUBLISH_STATS_DAYS)
    for s in CATALOG:
        if s.id not in where:
            continue
        kind, region, lat, lon = where[s.id]
        for o in istore.history(s.id):
            if period_date(o.period) >= horizon:
                rows.append((s.id, o.period, o.value, False, s.name, s.unit, kind, region, lat, lon, s.source_url))
        if (cur := running.get(s.id)):
            rows.append((s.id, cur["period"], cur["value"], True, s.name, s.unit, kind, region, lat, lon, s.source_url))
    return rows


def _event_row(e: LiveEvent) -> tuple:
    return (e.id, e.feed, e.kind, e.title, e.detail, e.lat, e.lon, e.countries, e.severity, e.start or None, e.end,
            e.source_url, e.source, e.tags, json.dumps(e.data, ensure_ascii=False).replace("\\u0000", ""))


def publish(feed_events: dict[str, list[LiveEvent]], *, with_stats: bool = True, today: date | None = None,
            connect: Callable[[], Any] | None = None) -> dict[str, Any]:
    """Upsert the given feeds' current events (retiring the rest of those feeds) and, optionally, the stats."""
    today = today or date.today()

    def work(conn: Any) -> dict:
        n_events = 0
        with conn.cursor() as cur:
            for feed, events in feed_events.items():
                for e in events:
                    cur.execute(_EVENT, _event_row(e))
                cur.execute(_RETIRE, (feed, [e.id for e in events]))
                n_events += len(events)
            rows = stat_rows(today) if with_stats else []
            for row in rows:
                cur.execute(_STAT, row)
        return {"events": n_events, "stats": len(rows)}

    return _run(work, connect)


def publish_world(*, force: bool = False, connect: Callable[[], Any] | None = None) -> dict[str, Any]:
    """Publish the /live page's basemap (document ``live/world.json``) once; ``force`` re-sends it."""
    from algent_backend.publishing.published_db import publish_documents

    from . import worldmap

    marker = store.root() / "world_published"
    if marker.exists() and not force:
        return {"db": True, "world": "already published"}
    world = worldmap.build()
    if world is None:
        return {"db": False, "note": "no Natural Earth basemap on this machine"}
    res = publish_documents({"live/world.json": world}, connect=connect)
    if res.get("db"):
        marker.parent.mkdir(parents=True, exist_ok=True)
        marker.write_text("1", encoding="utf-8")
    return res
