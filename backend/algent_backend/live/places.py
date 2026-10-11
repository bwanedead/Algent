"""
Places for live events — which country a point is in, and where a country sits on a map.

Reuses the desk's Natural Earth basemap (``intel/geo.py``). Everything degrades to "unknown": with no basemap an
event simply carries no country or no coordinates, it is never dropped or guessed.
"""

from __future__ import annotations

from typing import Any


def _geo() -> Any:
    from algent_backend.agent_system.agents.intel import geo

    return geo


def _countries() -> list[Any]:
    try:
        return _geo().load() or []
    except Exception:  # noqa: BLE001 - a missing basemap must never stop a collector
        return []


def country_at(lat: float, lon: float) -> str | None:
    """Name of the country whose land contains the point (None at sea or without a basemap)."""
    geo = _geo()
    for c in _countries():
        if c.bbox[0] <= lon <= c.bbox[2] and c.bbox[1] <= lat <= c.bbox[3] and geo.contains(c, lon, lat):
            return c.name
    return None


def by_code(iso2: str) -> Any | None:
    key = (iso2 or "").strip().lower()
    return next((c for c in _countries() if key and key in c.keys and len(key) == 2), None)


def centroid(country: Any) -> tuple[float, float]:
    """(lat, lon): centre of the bounding box of the country's largest piece of land (a rough label anchor)."""
    best = max(country.polygons, key=lambda poly: len(poly[0]) if poly else 0)
    xs, ys = [p[0] for p in best[0]], [p[1] for p in best[0]]
    return round((min(ys) + max(ys)) / 2, 3), round((min(xs) + max(xs)) / 2, 3)
