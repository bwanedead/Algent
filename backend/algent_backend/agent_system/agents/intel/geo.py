"""
Where-it-happened maps for the daily report, from our own data and plain Python math.

The section writer proposes ``place: {name, country, lat, lon}`` for a development (its best coordinates
for a named city or site). A model's coordinates are a claim, so this module VALIDATES every one against
the Natural Earth 110m countries file (public domain) and drops what does not hold; it never "fixes" one:

- the country must exist in the file (matched on NAME / ADMIN / ISO codes, case-insensitive);
- the point must lie inside that country's polygon, or within ``NEAR_BORDER_KM`` of its border (the 110m
  geometry is coarse, so coastal cities sit a little outside it);
- MARITIME: country "sea" (or empty / "maritime" / "international waters") is allowed for sea lanes such
  as Hormuz or Bab el-Mandeb. Kept simple: a maritime point is rejected only when it lies inside a country
  and further than ``NEAR_BORDER_KM`` from that country's border (that is land, not water).

``build_map`` then turns the validated points into a self-contained spec the site draws without external
data: an equirectangular frame (x linear in longitude, y linear in latitude, aspect corrected by
cos(mid-latitude)), the countries that touch the frame as compact SVG paths, and the points. Shape:

    {"bbox":[w,s,e,n],"projection":"equirectangular","width":1000,"height":int,
     "countries":[{"name","d"}],               # d in the 0..width x 0..height frame, clipped to the bbox
     "points":[{"x","y","label","date","verification","n"}],   # n = 1-based: developments[n-1]
     "credit":str}

No validated point, no map (None). Pure functions; no shapely.
"""

from __future__ import annotations

import json
import math
import os
import subprocess
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

NEAR_BORDER_KM = 50.0
MAP_WIDTH = 1000
MIN_SPAN_DEG = 8.0              # a single point still shows its region
PAD = 0.25                      # of the span, each side
MIN_ASPECT, MAX_ASPECT = 0.4, 1.6   # height/width of the frame
CREDIT = "Base map: Natural Earth (public domain). Locations: Ohmega, from today's developments; approximate."
_SEA = {"", "sea", "maritime", "ocean", "international waters", "strait"}
_ID_FIELDS = ("NAME", "ADMIN", "NAME_LONG", "SOVEREIGNT", "GEOUNIT", "BRK_NAME", "FORMAL_EN", "ISO_A2", "ISO_A3",
              "ADM0_A3", "ABBREV")
_ALIASES = {"united states": "united states of america", "us": "united states of america",
            "uk": "united kingdom", "russian federation": "russia", "iran, islamic republic of": "iran",
            "uae": "united arab emirates", "burma": "myanmar"}
_NATURAL_EARTH = ("analytics_workspace", "data", "natural_earth", "ne_110m_admin_0_countries.geojson")
_ENV = "ALGENT_NATURAL_EARTH"
Ring = list[tuple[float, float]]     # (lon, lat)


@dataclass
class Country:
    name: str
    keys: set[str]
    polygons: list[list[Ring]]       # each polygon: outer ring first, holes after
    bbox: tuple[float, float, float, float] = field(default=(0.0, 0.0, 0.0, 0.0))


# ── loading ───────────────────────────────────────────────────────────────────────────────────
def _main_checkout(here: Path) -> Path | None:
    """The main checkout of this repo (a worktree does not carry untracked data files)."""
    try:
        out = subprocess.run(["git", "rev-parse", "--git-common-dir"], cwd=str(here), capture_output=True,
                             text=True, timeout=20).stdout.strip()
    except (OSError, subprocess.SubprocessError):
        return None
    return (Path(out) if Path(out).is_absolute() else here / out).resolve().parent if out else None


def default_path() -> Path | None:
    """``$ALGENT_NATURAL_EARTH``, else the file under this checkout's root, else under the main checkout's."""
    if os.environ.get(_ENV):
        return Path(os.environ[_ENV])
    here = Path(__file__).resolve().parent
    root = next((p for p in here.parents if (p / "AGENTS.md").is_file() and (p / "backend").is_dir()), None)
    for base in (root, _main_checkout(here)):
        if base is not None and (base.joinpath(*_NATURAL_EARTH)).is_file():
            return base.joinpath(*_NATURAL_EARTH)
    return None


def _rings(geometry: dict) -> list[list[Ring]]:
    polys = [geometry["coordinates"]] if geometry.get("type") == "Polygon" else (
        geometry["coordinates"] if geometry.get("type") == "MultiPolygon" else [])
    return [[[(float(x), float(y)) for x, y, *_ in ring] for ring in poly] for poly in polys]


def parse(data: dict) -> list[Country]:
    out = []
    for feat in data.get("features", []):
        props, polys = feat.get("properties") or {}, _rings(feat.get("geometry") or {})
        if not polys:
            continue
        keys = {str(props[k]).strip().lower() for k in _ID_FIELDS if props.get(k) not in (None, "", "-99")}
        pts = [p for poly in polys for ring in poly for p in ring]
        out.append(Country(name=str(props.get("NAME") or props.get("ADMIN") or ""), keys=keys, polygons=polys,
                           bbox=(min(p[0] for p in pts), min(p[1] for p in pts),
                                 max(p[0] for p in pts), max(p[1] for p in pts))))
    return out


_CACHE: dict[str, list[Country]] = {}


def load(path: Path | None = None) -> list[Country] | None:
    """The countries from a Natural Earth GeoJSON; None when the file is missing or unreadable (the report
    then simply has no places or maps)."""
    path = path or default_path()
    if path is None:
        return None
    key = str(path)
    if key not in _CACHE:
        try:
            _CACHE[key] = parse(json.loads(path.read_text(encoding="utf-8")))
        except (OSError, ValueError):
            return None
    return _CACHE[key]


# ── geometry ──────────────────────────────────────────────────────────────────────────────────
def _in_ring(lon: float, lat: float, ring: Ring) -> bool:
    inside, j = False, len(ring) - 1
    for i, (xi, yi) in enumerate(ring):
        xj, yj = ring[j]
        if (yi > lat) != (yj > lat) and lon < (xj - xi) * (lat - yi) / (yj - yi) + xi:
            inside = not inside
        j = i
    return inside


def contains(country: Country, lon: float, lat: float) -> bool:
    for poly in country.polygons:
        if poly and _in_ring(lon, lat, poly[0]) and not any(_in_ring(lon, lat, hole) for hole in poly[1:]):
            return True
    return False


def border_km(country: Country, lon: float, lat: float) -> float:
    """Distance from the point to the nearest border segment, in km (local flat approximation)."""
    kx, ky = 111.32 * math.cos(math.radians(lat)), 110.57
    best = math.inf
    for poly in country.polygons:
        for ring in poly:
            for (x1, y1), (x2, y2) in zip(ring, ring[1:] + ring[:1], strict=True):
                ax, ay, bx, by = (x1 - lon) * kx, (y1 - lat) * ky, (x2 - lon) * kx, (y2 - lat) * ky
                dx, dy = bx - ax, by - ay
                t = 0.0 if dx == dy == 0 else max(0.0, min(1.0, -(ax * dx + ay * dy) / (dx * dx + dy * dy)))
                best = min(best, math.hypot(ax + t * dx, ay + t * dy))
    return best


def find_country(countries: list[Country], name: str) -> Country | None:
    key = (name or "").strip().lower()
    key = _ALIASES.get(key, key)
    return next((c for c in countries if key in c.keys), None) if key else None


def validate_place(place: Any, countries: list[Country] | None) -> dict | None:
    """The place as a clean dict, or None when it does not hold (never adjusted)."""
    if place is None or not countries:
        return None
    try:
        lat, lon = float(place.lat), float(place.lon)
    except (TypeError, ValueError):
        return None
    name = (place.name or "").strip()
    if not name or not (math.isfinite(lat) and math.isfinite(lon)) or abs(lat) > 90 or abs(lon) > 180:
        return None
    country = (place.country or "").strip()
    if country.lower() in _SEA:
        for c in countries:
            if c.bbox[0] <= lon <= c.bbox[2] and c.bbox[1] <= lat <= c.bbox[3] and contains(c, lon, lat) \
                    and border_km(c, lon, lat) > NEAR_BORDER_KM:
                return None                                  # inland, not a sea lane
        country = "sea"
    else:
        c = find_country(countries, country)
        if c is None:
            return None
        if not contains(c, lon, lat) and border_km(c, lon, lat) > NEAR_BORDER_KM:
            return None
        country = c.name
    return {"name": name, "country": country, "lat": round(lat, 4), "lon": round(lon, 4)}


# ── the map ───────────────────────────────────────────────────────────────────────────────────
def _frame(points: list[tuple[float, float]]) -> tuple[float, float, float, float]:
    """bbox [w,s,e,n]: the points, padded, never thinner than MIN_SPAN_DEG, with a sane aspect, inside the world."""
    lons, lats = [p[0] for p in points], [p[1] for p in points]
    w, e, s, n = min(lons), max(lons), min(lats), max(lats)
    mid_lon, mid_lat = (w + e) / 2, (s + n) / 2
    lon_span = max((e - w) * (1 + 2 * PAD), MIN_SPAN_DEG)
    lat_span = max((n - s) * (1 + 2 * PAD), MIN_SPAN_DEG)
    cos = max(math.cos(math.radians(mid_lat)), 0.2)
    aspect = lat_span / (lon_span * cos)
    if aspect > MAX_ASPECT:
        lon_span = lat_span / (MAX_ASPECT * cos)
    elif aspect < MIN_ASPECT:
        lat_span = lon_span * cos * MIN_ASPECT
    lon_span, lat_span = min(lon_span, 360.0), min(lat_span, 180.0)
    w = max(-180.0, min(mid_lon - lon_span / 2, 180.0 - lon_span))
    s = max(-90.0, min(mid_lat - lat_span / 2, 90.0 - lat_span))
    return w, s, w + lon_span, s + lat_span


def _fmt(v: float) -> str:
    return f"{v:.1f}".removesuffix(".0")


def _clip(ring: list[tuple[float, float]], box: tuple[float, float, float, float]) -> list[tuple[float, float]]:
    """Sutherland-Hodgman against the frame rectangle (x0, y0, x1, y1)."""
    x0, y0, x1, y1 = box
    edges = ((lambda p: p[0] >= x0, lambda a, b: (x0, a[1] + (b[1] - a[1]) * (x0 - a[0]) / (b[0] - a[0]))),
             (lambda p: p[0] <= x1, lambda a, b: (x1, a[1] + (b[1] - a[1]) * (x1 - a[0]) / (b[0] - a[0]))),
             (lambda p: p[1] >= y0, lambda a, b: (a[0] + (b[0] - a[0]) * (y0 - a[1]) / (b[1] - a[1]), y0)),
             (lambda p: p[1] <= y1, lambda a, b: (a[0] + (b[0] - a[0]) * (y1 - a[1]) / (b[1] - a[1]), y1)))
    for inside, cut in edges:
        src, ring = ring, []
        for i, cur in enumerate(src):
            prev = src[i - 1]
            if inside(cur):
                if not inside(prev):
                    ring.append(cut(prev, cur))
                ring.append(cur)
            elif inside(prev):
                ring.append(cut(prev, cur))
        if not ring:
            return []
    return ring


def _path(rings: list[list[tuple[float, float]]]) -> str:
    parts = []
    for ring in rings:
        kept = [ring[0]]
        for x, y in ring[1:]:
            if math.hypot(x - kept[-1][0], y - kept[-1][1]) >= 1.0:       # skip vertices within ~1px
                kept.append((x, y))
        if len(kept) >= 3:
            parts.append("M" + "L".join(f"{_fmt(x)} {_fmt(y)}" for x, y in kept) + "Z")
    return "".join(parts)


def build_map(developments: list[dict], countries: list[Country] | None) -> dict | None:
    """The where-it-happened spec for a theater, from developments whose ``place`` already validated."""
    if not countries:
        return None
    pts = [(i + 1, d["place"], d) for i, d in enumerate(developments) if d.get("place")]
    if not pts:
        return None
    w, s, e, n = _frame([(p["lon"], p["lat"]) for _, p, _ in pts])
    cos = max(math.cos(math.radians((s + n) / 2)), 0.2)
    height = max(1, round(MAP_WIDTH * (n - s) / ((e - w) * cos)))
    sx, sy = MAP_WIDTH / (e - w), height / (n - s)

    def proj(lon: float, lat: float) -> tuple[float, float]:
        return (lon - w) * sx, (n - lat) * sy

    out = []
    for c in countries:
        if c.bbox[2] < w or c.bbox[0] > e or c.bbox[3] < s or c.bbox[1] > n:
            continue
        rings = []
        for poly in c.polygons:
            for ring in poly:
                if max(x for x, _ in ring) < w or min(x for x, _ in ring) > e \
                        or max(y for _, y in ring) < s or min(y for _, y in ring) > n:
                    continue
                clipped = _clip([proj(x, y) for x, y in ring], (0.0, 0.0, float(MAP_WIDTH), float(height)))
                if clipped:
                    rings.append(clipped)
        d = _path(rings)
        if d:
            out.append({"name": c.name, "d": d})
    points = []
    for n_, place, dev in pts:
        x, y = proj(place["lon"], place["lat"])
        points.append({"x": round(x, 1), "y": round(y, 1), "label": place["name"], "date": dev.get("when", ""),
                       "verification": dev.get("verification", "reported"), "n": n_})
    return {"bbox": [round(w, 3), round(s, 3), round(e, 3), round(n, 3)], "projection": "equirectangular",
            "width": MAP_WIDTH, "height": height, "countries": out, "points": points, "credit": CREDIT}
