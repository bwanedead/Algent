"""
Publish sanctions events to the site database (migration 012: ``sanctions_events``, anon read-only).

Same contract as ``geoledger/publish`` and ``publishing/published_db``: never raises, idempotent, a no-op without
``DATABASE_URL``. The event log is append-only, so a watermark (``published.json``: lines already sent) lets each run send
only what is new; ``full=True`` resends the recent window.
"""

from __future__ import annotations

from collections.abc import Callable
from datetime import date, timedelta
from typing import Any

from algent_backend.publishing import published_db, site_data
from algent_backend.publishing.published_db import _run

from . import flags, store
from .contracts import SanctionsEvent
from .vessels import asset_id

_ROW = """
insert into sanctions_events (id, source, action, on_date, observed_on, ref, name, type, programmes, countries, imo, flag, owner,
                              source_url, baseline, asset_id)
values (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
on conflict (id) do nothing
"""


def row(e: SanctionsEvent) -> tuple:
    return (e.id, e.source, e.action, e.date, e.observed_on, e.ref, e.name, e.type, e.programmes, e.countries, e.imo, e.flag, e.owner,
            e.source_url, e.baseline, asset_id(e) if e.type == "vessel" and e.action == "designated" else None)


#: The site's windows: the page and the API show up to 180 days (``recentSanctions`` / ``sanctionsForCountry`` in lib/sanctions.ts); a country
#: file carries that country's events, newest first. Row cap = the old query's ``limit``.
WINDOW_DAYS = 180
RECENT_MAX = 3000
COUNTRY_MAX = 200
COLUMNS = ("id", "source", "action", "on_date", "observed_on", "ref", "name", "type", "programmes", "countries", "imo", "flag", "owner",
           "source_url", "baseline", "asset_id")


def documents(today: date | None = None) -> dict[str, Any]:
    """``sanctions/recent.json`` (all events of the last ``WINDOW_DAYS``) and ``sanctions/country/<ISO>.json`` (one country's, for its actor page)."""
    horizon = ((today or date.today()) - timedelta(days=WINDOW_DAYS)).isoformat()
    rows = [dict(zip(COLUMNS, row(e))) for e in store.events() if e.date >= horizon]
    rows.sort(key=lambda r: (r["on_date"], r["observed_on"], r["id"]), reverse=True)
    docs: dict[str, Any] = {"sanctions/recent.json": {"rows": rows[:RECENT_MAX]}}
    by_country: dict[str, list[dict[str, Any]]] = {}
    for r in rows:
        for iso in r["countries"]:
            if len(iso) == 2 and len(by_country.setdefault(iso.upper(), [])) < COUNTRY_MAX:
                by_country[iso.upper()].append(r)
    docs.update({f"sanctions/country/{iso}.json": {"rows": rs} for iso, rs in sorted(by_country.items())})
    return docs


def publish(*, full: bool = False, today: date | None = None, connect: Callable[[], Any] | None = None) -> dict[str, Any]:
    files = site_data.publish_built(lambda: documents(today))
    if published_db.files_only(connect):
        if files.get("ok"):
            store.save_published(store.line_count())        # the watermark still moves: "sent" now means "in the documents"
        return files
    out = _publish_table(full=full, today=today, connect=connect)
    if files.get("ok"):
        out["files"] = files
    return out


def _publish_table(*, full: bool = False, today: date | None = None, connect: Callable[[], Any] | None = None) -> dict[str, Any]:
    total = store.line_count()
    if full:
        horizon = ((today or date.today()) - timedelta(days=flags.PUBLISH_DAYS)).isoformat()
        pending = [e for e in store.events() if e.date >= horizon]
    else:
        pending = store.event_lines_after(store.published_count())
    if not pending:
        return {"db": True, "events": 0, "note": "nothing new"}

    def work(conn: Any) -> dict:
        with conn.cursor() as cur:
            cur.executemany(_ROW, [row(e) for e in pending])
        return {"events": len(pending)}

    result = _run(work, connect)
    if result.get("db"):
        store.save_published(total)             # only after the commit: a failed publish is retried whole
    return result
