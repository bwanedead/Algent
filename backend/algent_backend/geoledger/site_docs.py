"""
The ledger as site documents - what ``geo_assets`` / ``geo_asset_events`` / ``geo_grid`` used to serve (docs/architecture/published-content.md).

The site no longer queries a database, so each question it asked gets a bounded file:

    geo/countries.json          [{iso, n, n_events, bbox}]: which country files exist and where their places lie (a map frame picks files by bbox)
    geo/c/<ISO>.json            {assets: [...]}: every place WITH a status event plus the largest ``STATIC_PER_COUNTRY`` without one ("ZZ": no country)
    geo/events-assets.json      {assets: [...]}: the places with events, most events first (API lists, the sitemap)
    geo/a/<id>.json             {asset, events}: one place and its whole history (a place page); a merged duplicate keeps a stub that points at its target
    geo/events/<YYYY-MM>.json   {events: [...]}: every event dated in that month, newest first (a theater's "Strike & status log" window)
    geo/grid/<ISO>.json         the grid-impact rollup of one country (``grid.publish_rollups``)

Rows have exactly the columns the table had (``publish.asset_row`` / ``event_row``), so the site's parsers are unchanged. Places with no event
and outside a country's largest ``STATIC_PER_COUNTRY`` are not published (the map would not draw them under its 500-place cap either); they
remain in the ledger, the system of record.
"""

from __future__ import annotations

import json
from typing import Any

from . import publish as table
from .store import Ledger

ASSET_COLS = ("id", "name", "aliases", "type", "country", "lat", "lon", "loc_precision", "capacity_mw", "fuel", "attrs", "source", "licence",
              "provenance", "status", "status_on", "status_by", "events", "merged_into")
EVENT_COLS = ("id", "asset_id", "occurred_on", "occurred_at", "status", "claimant", "confidence", "sources", "provenance", "observed_at", "note", "via")
STATIC_PER_COUNTRY = 2000
EVENT_ASSETS_MAX = 2000
NO_COUNTRY = "ZZ"


def _asset(ledger: Ledger, asset_id: str) -> dict[str, Any]:
    a = ledger.assets[asset_id]
    merged = ledger.merged.get(asset_id)
    row = dict(zip(ASSET_COLS, table.asset_row(a, None if merged else ledger.status(asset_id), 0 if merged else len(ledger.by_asset.get(asset_id, [])), merged)))
    row["attrs"] = json.loads(row["attrs"]) if isinstance(row["attrs"], str) else row["attrs"]
    return row


def _event(ledger: Ledger, e: Any) -> dict[str, Any]:
    return dict(zip(EVENT_COLS, table.event_row(e, ledger.canonical(e.asset_id))))


def _bbox(rows: list[dict[str, Any]]) -> list[float] | None:
    pts = [(r["lon"], r["lat"]) for r in rows if r["lat"] is not None and r["lon"] is not None]
    if not pts:
        return None
    return [min(p[0] for p in pts), min(p[1] for p in pts), max(p[0] for p in pts), max(p[1] for p in pts)]


def documents(ledger: Ledger | None = None) -> dict[str, Any]:
    ledger = ledger or Ledger()
    live = ledger.live()
    docs: dict[str, Any] = {}
    evented = [a for a in live if ledger.by_asset.get(a.id)]
    by_country: dict[str, list] = {}
    for a in live:
        by_country.setdefault((a.country or NO_COUNTRY).upper(), []).append(a)
    index = []
    for iso, assets in sorted(by_country.items()):
        has = [a for a in assets if ledger.by_asset.get(a.id)]
        static = sorted((a for a in assets if not ledger.by_asset.get(a.id)),
                        key=lambda a: (-(float(a.attrs.get("capacity_mw")) if isinstance(a.attrs.get("capacity_mw"), (int, float)) else -1.0), a.id))
        rows = [_asset(ledger, a.id) for a in [*has, *static[:STATIC_PER_COUNTRY]]]
        docs[f"geo/c/{iso}.json"] = {"assets": rows}
        index.append({"iso": iso, "n": len(assets), "n_events": len(has), "bbox": _bbox(rows)})
    docs["geo/countries.json"] = {"countries": index}
    ev_rows = sorted((_asset(ledger, a.id) for a in evented), key=lambda r: (-r["events"], -(r["capacity_mw"] or 0), r["id"]))
    docs["geo/events-assets.json"] = {"assets": ev_rows[:EVENT_ASSETS_MAX]}
    for r in ev_rows:
        docs[f"geo/a/{r['id']}.json"] = {"asset": r, "events": [_event(ledger, e) for e in ledger.history(r["id"])]}
    for dup in sorted(ledger.merged):
        if dup in ledger.assets:
            docs[f"geo/a/{dup}.json"] = {"asset": _asset(ledger, dup), "events": []}
    months: dict[str, list[dict[str, Any]]] = {}
    for e in ledger.events.values():
        months.setdefault(e.occurred_on[:7], []).append(_event(ledger, e))
    for month, rows in sorted(months.items()):
        rows.sort(key=lambda r: (r["occurred_on"], r["observed_at"], r["id"]), reverse=True)
        docs[f"geo/events/{month}.json"] = {"events": rows}
    return docs
