"""
The published ``satellite`` document (``live/satellite.json`` in the public bucket): the watch list with, per site, its before / after chips and
the verdicts. Every verdict is a machine signal and carries its provenance (``basis``, ``method_note``, ``baseline_since``, ``n_obs``), so the site
can say how much history a number rests on. Chip paths are bucket keys (``satellite/<site>/<date>-<hash>.png``).
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from . import store
from .watchlist import Site, bbox_of

CREDIT = ("Contains modified Copernicus Sentinel data (ESA), served by Microsoft Planetary Computer; processed by Ohmega. "
          "Night lights: NASA VIIRS via GIBS (NASA EOSDIS).")
READ_AS = ("Every change score is a machine signal computed here from two pictures of the same ground: it says pixels differ, never what changed or why. "
           "A cloudy pair is inconclusive, not change. A site flagged 'changed' is far outside its own earlier scores; with few earlier looks it is 'learning' "
           "and nothing is flagged.")


def _links(s: Site) -> dict[str, str]:
    out = {}
    if s.asset_id:
        out["asset"] = s.asset_id
    if s.country:
        out["country"] = s.country
    if s.theater:
        out["theater"] = s.theater
    return out


def site_entry(s: Site) -> dict[str, Any]:
    st = store.read_json(f"sites/{s.id}/state.json", {}) or {}
    j = st.get("judgement") or {}
    return {"id": s.id, "name": s.name, "kind": s.kind, "asset_type": s.asset_type, "lat": s.lat, "lon": s.lon, "half_km": s.half_km,
            "bbox": list(bbox_of(s.lat, s.lon, s.half_km)), "priority": s.priority, "why": s.why, "event_on": s.event_on or None,
            "countries": s.countries, "links": _links(s), "state": st.get("state", "pending"), "note": st.get("note", ""),
            "checked_at": datetime.fromtimestamp(st["checked_at"], timezone.utc).isoformat(timespec="seconds") if st.get("checked_at") else None,
            "baseline": st.get("baseline"), "latest": st.get("latest"), "change": j or None, "night": st.get("night")}


def build(sites: list[Site], now: datetime, *, budget: dict[str, Any] | None = None) -> dict[str, Any]:
    entries = [site_entry(s) for s in sites]
    return {"v": 1, "as_of": now.isoformat(timespec="seconds"), "credit": CREDIT, "read_as": READ_AS, "pass": budget or {},
            "counts": {"watched": len(entries), "with_imagery": sum(1 for e in entries if e["latest"]),
                       "changed": sum(1 for e in entries if (e["change"] or {}).get("label") == "changed"),
                       "dimmer": sum(1 for e in entries if (e["night"] or {}).get("label") == "dimmer")},
            "sites": entries}


def chip_keys(doc: dict[str, Any]) -> list[str]:
    """Every chip the document points at (bucket keys), baseline and latest."""
    keys = []
    for e in doc["sites"]:
        for m in (e.get("baseline"), e.get("latest")):
            if m and m.get("chip") and m["chip"] not in keys:
                keys.append(m["chip"])
    return keys
