"""
Attack events and GPS-interference zones as view blocks: one place that reads the two products' documents (``conflict/…``, ``gnss/latest.json``) for the country,
situation and globe-HUD views, so the three never describe them differently.

Both blocks are None when the product has published nothing (a view never carries an empty block that looks like "no attacks"). Counts are the documents' own
(the whole stored window, not the rows shown); rows are the strongest first. Provenance travels with the block: the site words it through the stats registry.
"""

from __future__ import annotations

from typing import Any

from . import dailies, flags
from .context import ViewContext

_ROW = ("id", "source", "on_date", "type", "lat", "lon", "place", "country", "fatalities", "articles", "coding", "confidence", "basis")
_ZONE = ("id", "country", "lat", "lon", "severity", "degraded_share", "aircraft", "flag", "cross_check")


def _event(r: dict[str, Any]) -> dict[str, Any]:
    urls = dailies.strs(r.get("urls"))
    return {**{k: r.get(k) for k in _ROW}, "url": urls[0] if urls else "", "title": r.get("title") or r.get("place") or ""}


def _sources(doc: dict[str, Any]) -> dict[str, Any]:
    return {"since": doc.get("since") or "", "sources": {k: bool((v or {}).get("active")) for k, v in (doc.get("sources") or {}).items()}}


def attacks_of(ctx: ViewContext, iso: str, limit: int = flags.COUNTRY_ATTACKS) -> dict[str, Any] | None:
    """The country's strongest events of the last ``window_days`` days and how many were stored in all."""
    doc = ctx.table(f"conflict/country/{iso}.json")
    if not isinstance(doc, dict) or not doc.get("rows"):
        return None
    rows = dailies.objs(doc.get("rows"))
    recent = ctx.table("conflict/recent.json")
    return {"total": int(doc.get("total") or len(rows)), "capped": bool(doc.get("capped")), "window_days": int(doc.get("window_days") or 0), "as_of": doc.get("as_of") or "",
            **(_sources(recent) if isinstance(recent, dict) else {}), "rows": [_event(r) for r in rows[:limit]]}


def attacks_recent(ctx: ViewContext, days: int, limit: int) -> dict[str, Any] | None:
    """The strongest events of the newest ``days`` days anywhere (the globe panel) with the count of every stored event in that window."""
    doc = ctx.table("conflict/recent.json")
    if not isinstance(doc, dict) or not doc.get("rows"):
        return None
    floor = _days_back(ctx.today, days)
    rows = [r for r in dailies.objs(doc.get("rows")) if str(r.get("on_date")) >= floor]
    by_day = doc.get("by_day") if isinstance(doc.get("by_day"), dict) else {}
    total = sum(int((v or {}).get("events") or 0) for d, v in by_day.items() if d >= floor)
    return {"total": total or len(rows), "days": days, "as_of": doc.get("as_of") or "", **_sources(doc),
            "rows": [_event(r) for r in sorted(rows, key=lambda r: (r.get("coding") == "curated", r.get("fatalities") or 0, r.get("articles") or 0), reverse=True)[:limit]]}


def gnss_in(ctx: ViewContext, isos: set[str] | None, limit: int) -> dict[str, Any] | None:
    """Our latest-day zones (all of them, or those over ``isos``), flagged and strongest first. GPSJam's cells are a cross-check, not counted here."""
    doc = ctx.table("gnss/latest.json")
    if not isinstance(doc, dict):
        return None
    zones = [z for z in dailies.objs(doc.get("ours")) if isos is None or z.get("country") in isos]
    if not zones:
        return None
    zones.sort(key=lambda z: (not z.get("flag"), -float(z.get("degraded_share") or 0)))
    return {"day": doc.get("day") or "", "total": len(zones), "baseline_since": doc.get("baseline_since") or "", "baseline_days": int(doc.get("baseline_days") or 0),
            "zones": [{k: z.get(k) for k in _ZONE} for z in zones[:limit]]}


def _days_back(today: str, n: int) -> str:
    from datetime import date, timedelta

    return (date.fromisoformat(today) - timedelta(days=n)).isoformat()
