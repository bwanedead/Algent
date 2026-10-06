"""
The reference layers of a daily map: cities, rivers, lakes, disputed areas, and instrument annotations.

Natural Earth (public domain) supplies the first four; the numbers layer (``algent_backend.instruments``)
supplies the last. Loading is cheap and cached; every layer is optional, so a map degrades to land and
points when a file is missing. Selection is by rank and frame size, never a fixed list: a country-scale
frame shows many towns, a continent-scale frame only the largest cities and the capitals.

Frame coordinates are the map's own (0..width, 0..height); ``proj(lon, lat)`` projects into them.
"""

from __future__ import annotations

import json
import math
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import date
from pathlib import Path
from typing import Any

from .geo_disputed import Disputed, from_feature
from .geo_draw import Pt

FILES = {"cities": "ne_10m_populated_places_simple.geojson", "rivers": "ne_50m_rivers_lake_centerlines.geojson",
         "lakes": "ne_50m_lakes.geojson", "disputed": "ne_10m_admin_0_disputed_areas.geojson"}
DISPUTED_FALLBACK = "ne_50m_admin_0_breakaway_disputed_areas.geojson"    # lighter and without Gaza/West Bank
CITY_SPACING = 55.0            # frame units between non-capital cities: room for a ~12px label at ~0.7 px/unit
MIN_CITY_POP = 100_000
Proj = Callable[[float, float], Pt]


@dataclass
class City:
    name: str
    lon: float
    lat: float
    pop: int
    capital: bool
    country: str


@dataclass
class Layers:
    cities: list[City] = field(default_factory=list)
    rivers: list[tuple[float, list[list[Pt]]]] = field(default_factory=list)    # (min_zoom, lines (lon, lat))
    lakes: list[list[list[Pt]]] = field(default_factory=list)                    # polygons: outer ring + holes
    disputed: list[Disputed] = field(default_factory=list)                       # disputed / occupied areas (geo_disputed)


NO_LAYERS = Layers()
_CACHE: dict[tuple, Layers] = {}


def _features(path: Path | None) -> list[dict]:
    if path is None:
        return []
    try:
        return json.loads(path.read_text(encoding="utf-8")).get("features", [])
    except (OSError, ValueError):
        return []


def _lines(geom: dict) -> list[list[Pt]]:
    coords = [geom["coordinates"]] if geom.get("type") == "LineString" else (
        geom["coordinates"] if geom.get("type") == "MultiLineString" else [])
    return [[(float(x), float(y)) for x, y, *_ in line] for line in coords]


def _polys(geom: dict) -> list[list[list[Pt]]]:
    polys = [geom["coordinates"]] if geom.get("type") == "Polygon" else (
        geom["coordinates"] if geom.get("type") == "MultiPolygon" else [])
    return [[[(float(x), float(y)) for x, y, *_ in ring] for ring in poly] for poly in polys]


def load_layers(find: Callable[[str], Path | None], recognised: dict[str, tuple[float, float, float, float]]) -> Layers:
    """Layers from the Natural Earth files ``find(name)`` can locate. ``recognised`` is the {country: box}
    table that re-seats disputed places (Crimea is Ukraine) so a city is never labelled by de facto control."""
    paths = {k: find(n) for k, n in FILES.items()}
    paths["disputed"] = paths["disputed"] or find(DISPUTED_FALLBACK)
    key = tuple(str(p) for p in paths.values())
    if key in _CACHE:
        return _CACHE[key]
    cities = []
    for f in _features(paths["cities"]):
        p, g = f.get("properties") or {}, f.get("geometry") or {}
        if g.get("type") != "Point" or not p.get("name"):
            continue
        lon, lat = float(g["coordinates"][0]), float(g["coordinates"][1])
        country = str(p.get("adm0name") or "")
        for owner, (w, s, e, n) in recognised.items():
            if w <= lon <= e and s <= lat <= n and country.lower() != owner:
                country = owner.title()
        capital = p.get("adm0cap") == 1 and p.get("featurecla") == "Admin-0 capital"
        pop = int(p.get("pop_max") or 0)
        if capital or pop >= MIN_CITY_POP:
            cities.append(City(str(p["name"]), lon, lat, pop, capital, country))
    rivers = []
    for f in _features(paths["rivers"]):
        p = f.get("properties") or {}
        if p.get("featurecla") == "River":
            rivers.append((float(p.get("min_zoom") or 5.0), _lines(f.get("geometry") or {})))
    lakes = [poly for f in _features(paths["lakes"]) for poly in _polys(f.get("geometry") or {})]
    disputed = [a for f in _features(paths["disputed"])
                if (a := from_feature(f.get("properties") or {}, _polys(f.get("geometry") or {})))]
    _CACHE[key] = Layers(cities=cities, rivers=rivers, lakes=lakes, disputed=disputed)
    return _CACHE[key]


def zoom_of(lon_span: float) -> float:
    """A web-map-like zoom level for a frame ``lon_span`` degrees wide (world = 1)."""
    return math.log2(360.0 / max(lon_span, 1e-6)) + 1.0


def rivers_in_frame(layers: Layers, lon_span: float) -> list[list[list[Pt]]]:
    """The river lines worth drawing at this frame size (Natural Earth's own min_zoom, one level of slack)."""
    limit = zoom_of(lon_span) + 1.0
    return [lines for z, lines in layers.rivers if z <= limit]


def city_budget(lon_span: float) -> int:
    """How many non-capital cities a frame carries: ~22 at country scale, ~12 for a whole-world frame."""
    return max(6, min(22, round(220 / math.sqrt(max(lon_span, 1.0)))))


def capital_budget(lon_span: float) -> int:
    """Capitals a frame carries: all of a country-scale frame's (~60), ~25 of a world-scale one's."""
    return max(12, min(60, round(400 / math.sqrt(max(lon_span, 1.0)))))


def select_cities(layers: Layers, proj: Proj, frame: tuple[float, float, float, float], width: float, height: float,
                  lon_span: float, event_countries: set[str] | None = None) -> list[dict]:
    """Reference cities inside the frame, most important first. Capitals come first: at country scale every
    capital in frame is kept; as the frame widens the capitals are cut to the largest ``capital_budget`` — except
    the capitals of ``event_countries`` (where the marks are), which are always kept. The rest are the largest
    cities, thinned so none sits within ``CITY_SPACING`` of another, and a budget that shrinks as the frame
    widens. The reader thins further by real pixel size."""
    w, s, e, n = frame
    margin = 8.0
    inside = []
    for c in layers.cities:
        if w <= c.lon <= e and s <= c.lat <= n:
            x, y = proj(c.lon, c.lat)
            if margin <= x <= width - margin and margin <= y <= height - margin:
                inside.append((c, x, y))
    caps = sorted((t for t in inside if t[0].capital), key=lambda t: -t[0].pop)
    rest = sorted((t for t in inside if not t[0].capital), key=lambda t: -t[0].pop)
    own = {c.lower() for c in event_countries or ()}
    keep = [t for t in caps if t[0].country.lower() in own]
    chosen = keep + [t for t in caps if t not in keep][: max(0, capital_budget(lon_span) - len(keep))]
    budget = city_budget(lon_span)
    taken = 0
    for t in rest:
        if taken >= budget:
            break
        if all(math.hypot(t[1] - o[1], t[2] - o[2]) >= CITY_SPACING for o in chosen):
            chosen.append(t)
            taken += 1
    return [{"name": c.name, "x": round(x, 1), "y": round(y, 1), "capital": c.capital} for c, x, y in chosen]


# ── instrument annotations ────────────────────────────────────────────────────────────────────
def _count(v: float, unit: str = "") -> str:
    """"1 ship/day", "102 ships/day" (the unit goes singular at exactly one)."""
    return f"{v:,.0f} {unit.replace('ships', 'ship') if round(v) == 1 else unit}".strip()


def _day(period: str) -> str:
    d = date.fromisoformat(period[:10])
    return f"{d.day} {d:%b}"


def chokepoint_notes(frame: tuple[float, float, float, float], proj: Proj, focus: list[tuple[float, float]],
                     lon_span: float, as_of: date | None = None) -> list[dict]:
    """A callout for each tracked chokepoint inside the frame: its latest stored reading beside the same
    series a year earlier. Reads the instruments STORE only (never the network); public-display series only;
    returns [] when the store holds nothing. On a wide frame only chokepoints near an event point are shown,
    so a continental map is not papered with callouts."""
    try:
        from algent_backend.instruments.catalog import chokepoint_sites
        from algent_backend.instruments.evidence import moves_board
    except ImportError:
        return []
    w, s, e, n = frame
    sites = [c for c in chokepoint_sites() if w <= c["lon"] <= e and s <= c["lat"] <= n
             and (lon_span <= 60 or any(math.hypot(c["lon"] - lo, c["lat"] - la) <= 10 for lo, la in focus))]
    if not sites:
        return []
    try:
        board = {m["series_id"]: m for m in moves_board(["chokepoint"], as_of=as_of)}
    except Exception:  # noqa: BLE001 — a broken or empty store must never break a map
        return []
    out: list[dict[str, Any]] = []
    for c in sites:
        m = board.get(c["series_id"])
        if not m or not m.get("public_display"):
            continue
        ch = m["changes"]
        horizon = next((k for k in ("1y", "30d", "7d") if k in ch), None)
        ago = {"1y": "a year ago", "30d": "30 days ago", "7d": "a week ago"}.get(horizon or "", "")
        reading = _count(m["latest"]["value"], m["unit"])
        line1 = f"{reading} · {_count(ch[horizon]['from_value'])} {ago}" if horizon else reading
        x, y = proj(c["lon"], c["lat"])
        out.append({"kind": "chokepoint", "x": round(x, 1), "y": round(y, 1), "title": c["label"],
                    "lines": [line1, f"as of {_day(m['latest']['period'])}"], "series_id": c["series_id"],
                    "source": "IMF PortWatch"})
    return out
