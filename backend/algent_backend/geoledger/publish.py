"""
Publish the ledger to the site database (migration 009: ``geo_assets``, ``geo_asset_events``, anon read-only).

Same contract as ``live/publish`` and ``publishing/published_db``: never raises, idempotent, a no-op without
``DATABASE_URL`` (or with ``ALGENT_DB_PUBLISH=0``). Because the local files are append-only, the publisher keeps a
watermark (``published.json``: lines already sent) and sends only the assets whose revision or events are newer;
``full=True`` resends everything. Each asset row also carries its latest status (derived here from its events), so the
map reads one table to colour a place. Events are inserted once; the only thing ever changed on one is the asset it
points at, when ``newsroom geo merge`` joins two spellings of a place (the duplicate's row stays, marked ``merged_into``).
"""

from __future__ import annotations

import json
from collections.abc import Callable
from typing import Any

from algent_backend.publishing import published_db, site_data
from algent_backend.publishing.published_db import _run

from . import store
from .contracts import Asset, StatusEvent
from .store import Ledger

CHUNK = 500
_ASSET = """
insert into geo_assets (id, name, aliases, type, country, lat, lon, loc_precision, capacity_mw, fuel, attrs, source, licence,
                        provenance, status, status_on, status_by, events, merged_into)
values (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s::jsonb, %s, %s, %s, %s, %s, %s, %s, %s)
on conflict (id) do update
   set name = excluded.name, aliases = excluded.aliases, type = excluded.type, country = excluded.country,
       lat = excluded.lat, lon = excluded.lon, loc_precision = excluded.loc_precision, capacity_mw = excluded.capacity_mw,
       fuel = excluded.fuel, attrs = excluded.attrs, source = excluded.source, licence = excluded.licence,
       provenance = excluded.provenance, status = excluded.status, status_on = excluded.status_on,
       status_by = excluded.status_by, events = excluded.events, merged_into = excluded.merged_into, updated_at = now()
"""
_EVENT = """
insert into geo_asset_events (id, asset_id, occurred_on, occurred_at, status, claimant, confidence, sources, provenance,
                              observed_at, note, via)
values (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
on conflict (id) do update set asset_id = excluded.asset_id
"""


def asset_row(a: Asset, latest: StatusEvent | None, n_events: int, merged_into: str | None = None) -> tuple:
    attrs = {k: v for k, v in a.attrs.items() if k not in ("capacity_mw", "fuel")}
    cap = a.attrs.get("capacity_mw")
    return (a.id, a.name, a.aliases, a.type, a.country, a.lat, a.lon, a.precision,
            float(cap) if isinstance(cap, (int, float)) else None, str(a.attrs.get("fuel", "")),
            json.dumps(attrs, ensure_ascii=False).replace("\\u0000", ""), a.source, a.licence, a.provenance,
            latest.status if latest else None, latest.occurred_on if latest else None, latest.claimant if latest else None,
            n_events, merged_into)


def event_row(e: StatusEvent, asset_id: str | None = None) -> tuple:
    return (e.id, asset_id or e.asset_id, e.occurred_on, e.occurred_at, e.status, e.claimant, e.confidence, e.sources, e.provenance,
            e.observed_at or None, e.note, e.via)


def pending(ledger: Ledger, *, full: bool = False) -> tuple[list[str], list[StatusEvent], dict[str, int]]:
    """(asset ids to send, events to send, the new watermark)."""
    marker = {"assets": 0, "events": 0, "merges": 0} if full else store.load_marker(ledger.base)
    now = store.line_counts(ledger.base)
    ids: list[str] = []
    for line in store.lines_after("assets", marker["assets"], ledger.base):
        try:
            ids.append(Asset.model_validate_json(line).id)
        except ValueError:
            continue
    events: list[StatusEvent] = []
    for line in store.lines_after("events", marker["events"], ledger.base):
        try:
            events.append(StatusEvent.model_validate_json(line))
        except ValueError:
            continue
    for line in store.lines_after("merges", marker["merges"], ledger.base):      # a merge re-sends both rows and the moved events
        try:
            m = json.loads(line)
        except ValueError:
            continue
        ids += [m["dup"], m["into"]]
        events += [e for e in ledger.events.values() if ledger.canonical(e.asset_id) == m["into"] and e not in events]
    ids += [e.asset_id for e in events]
    return [i for i in dict.fromkeys(ids) if i in ledger.assets], events, now


def publish(ledger: Ledger | None = None, *, full: bool = False, connect: Callable[[], Any] | None = None) -> dict[str, Any]:
    ledger = ledger or Ledger()
    ids, events, now = pending(ledger, full=full)
    if not ids and not events:
        return {"db": True, "ok": True, "assets": 0, "events": 0, "note": "nothing new"}
    from . import site_docs

    files = site_data.publish_built(lambda: site_docs.documents(ledger))        # the site's source: per-country / per-place / per-month files
    if published_db.files_only(connect):
        if files.get("ok"):
            store.save_marker(now, ledger.base)                                  # "sent" now means "in the documents"
        return {**files, "assets": len(ids), "events": len(events)}

    def work(conn: Any) -> dict:
        with conn.cursor() as cur:
            rows = [asset_row(ledger.assets[i], None if i in ledger.merged else ledger.status(i),
                              0 if i in ledger.merged else len(ledger.by_asset.get(i, [])), ledger.merged.get(i)) for i in ids]
            for k in range(0, len(rows), CHUNK):
                cur.executemany(_ASSET, rows[k:k + CHUNK])
            ev = [event_row(e, ledger.canonical(e.asset_id)) for e in events]
            for k in range(0, len(ev), CHUNK):
                cur.executemany(_EVENT, ev[k:k + CHUNK])
        return {"assets": len(ids), "events": len(events)}

    result = _run(work, connect)
    if result.get("db"):
        store.save_marker(now, ledger.base)       # only after the commit: a failed publish is retried whole
    if files.get("ok"):
        result["files"] = files
    return result
