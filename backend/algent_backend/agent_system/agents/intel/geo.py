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

``build_map`` then turns the validated points into a self-contained spec (version 2) the site draws without
external data: an equirectangular frame (x linear in longitude, y linear in latitude, aspect corrected by
cos(mid-latitude)) in 0..width x 0..height units, and layers drawn in it, all clipped to the frame:

    {"version":2,"bbox":[w,s,e,n],"projection":"equirectangular","width":1000,"height":int,
     "countries":[{"name","d"}],                        # land, simplified (Douglas-Peucker) to ~0.4 px
     "labels":[{"name","x","y","r","key"}],             # where to write a country's name; r = room (inscribed radius)
     "rivers":[{"d"}], "lakes":[{"d"}],                 # polylines / polygons; "d" are SVG paths
     "disputed":[{"name","d","note","status","claimants":[..],"source","x","y","r"}],   # hatched; see geo_disputed; may be []
     "cities":[{"name","x","y","capital"}],            # capitals + the largest cities, most important first
     "annotations":[{"kind":"chokepoint","x","y","title","lines":[..],"series_id","source"}],  # instruments, may be []
     "scale":{"km","px","label"},                       # a round-number bar, true at mid-latitude
     "locator":{"width","height","d","rect":{x,y,w,h}}|null,   # world inset with the frame outlined
     "points":[{"x","y","label","date","verification","n"}],   # n = 1-based: developments[n-1]
     "credit":str}

Version 1 (no ``version``, no layers) and early version-2 maps (no ``disputed``) already stored in past daily
records still render: the site treats the missing keys as empty. Drawing prefers the 50m countries file and degrades to 110m (``default_path``). No
validated point, no map (None). Pure functions apart from reading the Natural Earth files and the instruments
STORE; no shapely.
"""

from __future__ import annotations

import json
import math
import os
import subprocess
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import date
from pathlib import Path
from typing import Any

from .geo_disputed import entry as disputed_entry, top_areas
from .geo_draw import anchor, clip_line, clip_ring, line_path, ring_area, ring_path, scale_bar, simplify
from .geo_layers import NO_LAYERS, Layers, chokepoint_notes, load_layers, rivers_in_frame, select_cities

__all__ = ["NO_LAYERS", "Country", "build_map", "contains", "default_layers", "load", "validate_place"]

NEAR_BORDER_KM = 50.0
MAP_WIDTH = 1000
MIN_SPAN_DEG = 12.0             # a single point still shows its region: ~1,300 km across at mid-latitudes
PAD = 0.35                      # of the span, each side: context to place the region, never a tight box
MIN_ASPECT, MAX_ASPECT = 0.5, 0.9   # height/width of the frame (drawn full width, so never a tall strip)
SIMPLIFY = 0.0006               # Douglas-Peucker tolerance for a MIN_SPAN_DEG frame, as a share of the frame width
MIN_LABEL_AREA = 400.0          # frame units^2 of visible land below which a country is not named
MAX_TOLERANCE = 2.0             # ... never coarser than this many frame units, however wide the frame
LOCATOR_W = 200                 # the world inset width in its own units (height is half)
CREDIT = "Base map: Natural Earth (public domain). Locations: Ohmega, from today's developments; approximate."
_SEA = {"", "sea", "maritime", "ocean", "international waters", "strait"}
_ID_FIELDS = ("NAME", "ADMIN", "NAME_LONG", "SOVEREIGNT", "GEOUNIT", "BRK_NAME", "FORMAL_EN", "ISO_A2", "ISO_A3",
              "ADM0_A3", "ABBREV")
_ALIASES = {"united states": "united states of america", "us": "united states of america",
            "uk": "united kingdom", "russian federation": "russia", "iran, islamic republic of": "iran",
            "uae": "united arab emirates", "burma": "myanmar"}
_NE_DIR = ("analytics_workspace", "data", "natural_earth")
_COUNTRY_FILES = ("ne_50m_admin_0_countries.geojson", "ne_110m_admin_0_countries.geojson")   # best first
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


def _bases() -> list[Path]:
    here = Path(__file__).resolve().parent
    root = next((p for p in here.parents if (p / "AGENTS.md").is_file() and (p / "backend").is_dir()), None)
    return [b for b in (root, _main_checkout(here)) if b is not None]


def find_file(name: str) -> Path | None:
    """A Natural Earth file by name: next to ``$ALGENT_NATURAL_EARTH`` if set, else under this checkout's root,
    else under the main checkout's (a worktree does not carry untracked data files)."""
    if os.environ.get(_ENV):
        cand = Path(os.environ[_ENV]).parent / name
        return cand if cand.is_file() else None
    return next((b.joinpath(*_NE_DIR, name) for b in _bases() if b.joinpath(*_NE_DIR, name).is_file()), None)


def default_path() -> Path | None:
    """``$ALGENT_NATURAL_EARTH``, else the best countries file found: 50m (drawing quality), else 110m."""
    if os.environ.get(_ENV):
        return Path(os.environ[_ENV])
    return next((p for n in _COUNTRY_FILES if (p := find_file(n)) is not None), None)


def default_layers() -> Layers:
    """Cities, rivers and lakes from the Natural Earth files on disk; empty (land and points only) when absent."""
    return load_layers(find_file, _RECOGNISED)


def _rings(geometry: dict) -> list[list[Ring]]:
    polys = [geometry["coordinates"]] if geometry.get("type") == "Polygon" else (
        geometry["coordinates"] if geometry.get("type") == "MultiPolygon" else [])
    return [[[(float(x), float(y)) for x, y, *_ in ring] for ring in poly] for poly in polys]


#: Natural Earth's default layer draws DE FACTO control, which puts Crimea inside Russia. Ohmega's base
#: maps draw internationally recognised borders (UN GA resolution 68/262); de facto control belongs to a
#: front-line layer from a source we may lawfully use (docs/editorial/map-data-sources.md), never to the
#: base map. So any piece of another country lying wholly inside this box is drawn — and validated — as
#: Ukraine. The box encloses the peninsula and nothing else of Russia's territory.
_RECOGNISED = {"ukraine": (32.3, 44.3, 36.7, 46.3)}   # Crimea, by its own extent


def _reassign(data: dict) -> dict:
    feats = data.get("features", [])
    by_name = {str((f.get("properties") or {}).get("NAME") or "").lower(): f for f in feats}
    for owner, (w, s, e, n) in _RECOGNISED.items():
        target = by_name.get(owner)
        if target is None:
            continue
        for feat in feats:
            geom = feat.get("geometry") or {}
            if feat is target or geom.get("type") != "MultiPolygon":
                continue
            keep, moved = [], []
            for poly in geom["coordinates"]:
                pts = [p for ring in poly for p in ring]
                inside = all(w <= p[0] <= e and s <= p[1] <= n for p in pts)
                (moved if inside else keep).append(poly)
            if moved and keep:
                geom["coordinates"] = keep
                tg = target.setdefault("geometry", {})
                base = tg["coordinates"] if tg.get("type") == "MultiPolygon" else [tg.get("coordinates")]
                tg["type"], tg["coordinates"] = "MultiPolygon", [*base, *moved]
    return data


def parse(data: dict) -> list[Country]:
    out = []
    for feat in _reassign(data).get("features", []):
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
def _off_map(points: list[tuple[float, float]]) -> set[int]:
    """Indexes of points too far from the rest to share one useful frame. One US point in a Russia–Ukraine
    section stretched that map from -121 to 107 degrees, where nothing could be read. The rule is relative to the
    points themselves: an outlier is more than 3x the median distance from the median point (a robust spread
    measure that one stray point cannot inflate) and further than MIN_SPAN_DEG, so a merely wide theater keeps
    every point. Needs 3+ points: with two there is no way to say which one is the stray."""
    if len(points) < 3:
        return set()
    lons, lats = sorted(p[0] for p in points), sorted(p[1] for p in points)
    mlon, mlat = lons[len(lons) // 2], lats[len(lats) // 2]
    cos = max(math.cos(math.radians(mlat)), 0.2)
    dist = [math.hypot((lon - mlon) * cos, lat - mlat) for lon, lat in points]
    median = sorted(dist)[len(dist) // 2]
    cut = max(3 * median, MIN_SPAN_DEG)
    out = {i for i, d in enumerate(dist) if d > cut}
    return out if len(out) < len(points) else set()


def _frame(points: list[tuple[float, float]]) -> tuple[float, float, float, float]:
    """bbox [w,s,e,n]: the points, padded for context, never thinner than MIN_SPAN_DEG (a reader must be able
    to place the region, so a few towns never get a tight box), with a sane aspect, inside the world."""
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


def _projector(frame: tuple[float, float, float, float]) -> tuple[Callable[[float, float], tuple[float, float]], int]:
    """Equirectangular projection into a MAP_WIDTH-wide frame, aspect corrected by cos(mid-latitude); (proj, height)."""
    w, s, e, n = frame
    cos = max(math.cos(math.radians((s + n) / 2)), 0.2)
    height = max(1, round(MAP_WIDTH * (n - s) / ((e - w) * cos)))
    sx, sy = MAP_WIDTH / (e - w), height / (n - s)
    return (lambda lon, lat: ((lon - w) * sx, (n - lat) * sy)), height


def _drawn(polys: list[list[list[tuple[float, float]]]], bbox: tuple[float, float, float, float], frame: tuple,
           proj: Callable, box: tuple) -> list[list[list[tuple[float, float]]]]:
    """Polygons (lon/lat rings) that touch the frame, projected and clipped to it: [[outer, *holes], ...]."""
    w, s, e, n = frame
    if bbox[2] < w or bbox[0] > e or bbox[3] < s or bbox[1] > n:
        return []
    out = []
    for poly in polys:
        if not poly or max(x for x, _ in poly[0]) < w or min(x for x, _ in poly[0]) > e \
                or max(y for _, y in poly[0]) < s or min(y for _, y in poly[0]) > n:
            continue
        outer = clip_ring([proj(x, y) for x, y in poly[0]], box)
        if outer:
            out.append([outer, *(c for ring in poly[1:] if (c := clip_ring([proj(x, y) for x, y in ring], box)))])
    return out


def simplify_tolerance(lon_span: float) -> float:
    """Douglas-Peucker tolerance in frame units, from the frame size. A MIN_SPAN_DEG frame gets 0.6 of 1000 units
    (~0.4 px at the usual render width: below what an eye separates, so coastlines look unsimplified). The frame
    is always 1000 units wide, so a wider frame packs more coastline into the same picture: the tolerance grows
    with sqrt(span) (capped), keeping a continental map's size and a village-scale one's detail both sensible."""
    return min(MAX_TOLERANCE, MAP_WIDTH * SIMPLIFY * max(1.0, math.sqrt(lon_span / MIN_SPAN_DEG)))


def _bounds(rings: list[list[tuple[float, float]]]) -> tuple[float, float, float, float]:
    pts = [p for ring in rings for p in ring]
    return min(p[0] for p in pts), min(p[1] for p in pts), max(p[0] for p in pts), max(p[1] for p in pts)


_LOCATOR: dict[int, str] = {}


def _locator(countries: list[Country], frame: tuple[float, float, float, float]) -> dict | None:
    """A small whole-world frame (equirectangular, LOCATOR_W x LOCATOR_W/2) with the map's bbox as a rectangle.
    Omitted when the map already covers most of the world's width (the inset would add nothing)."""
    w, s, e, n = frame
    if (e - w) > 0.5 * 360:
        return None
    key = id(countries)
    if key not in _LOCATOR:
        sc = LOCATOR_W / 360.0
        proj = lambda lon, lat: ((lon + 180) * sc, (90 - lat) * sc)             # noqa: E731
        rings = [[proj(x, y) for x, y in poly[0]] for c in countries for poly in c.polygons if poly]
        _LOCATOR[key] = ring_path(rings, tol=0.9, min_extent=2.5, places=0)   # ~0.6 px at its ~140 px render
    sc = LOCATOR_W / 360.0
    rw, rh = max((e - w) * sc, 3.0), max((n - s) * sc, 3.0)         # never smaller than a visible mark
    return {"width": LOCATOR_W, "height": LOCATOR_W // 2, "d": _LOCATOR[key],
            "rect": {"x": round((w + 180) * sc, 1), "y": round((90 - n) * sc, 1), "w": round(rw, 1), "h": round(rh, 1)}}


def build_map(developments: list[dict], countries: list[Country] | None, *, layers: Layers | None = None,
              as_of: date | None = None) -> dict | None:
    """The where-it-happened spec (version 2) for a theater, from developments whose ``place`` already validated.

    ``layers`` are the reference layers (cities, rivers, lakes); by default the Natural Earth files found on
    disk, and ``NO_LAYERS`` draws land and points only. ``as_of`` replays the instrument annotations for a date.
    """
    if not countries:
        return None
    pts = [(i + 1, d["place"], d) for i, d in enumerate(developments) if d.get("place")]
    if not pts:
        return None
    far = _off_map([(p["lon"], p["lat"]) for _, p, _ in pts])
    elsewhere = [f"{n_} {p['name']}" for i, (n_, p, _) in enumerate(pts) if i in far]
    pts = [pt for i, pt in enumerate(pts) if i not in far]
    frame = _frame([(p["lon"], p["lat"]) for _, p, _ in pts])
    w, s, e, n = frame
    proj, height = _projector(frame)
    box = (0.0, 0.0, float(MAP_WIDTH), float(height))
    tol = simplify_tolerance(e - w)

    land, labels = [], []
    for c in countries:
        polys = _drawn(c.polygons, c.bbox, frame, proj, box)
        d = ring_path([r for poly in polys for r in poly], tol)
        if not d:
            continue
        land.append({"name": c.name, "d": d})
        best = max(polys, key=lambda poly: ring_area(poly[0]))
        if ring_area(best[0]) >= MIN_LABEL_AREA and c.name:
            ax, ay, r = anchor(simplify(best[0], tol, closed=True), [simplify(h, tol, closed=True) for h in best[1:]])
            labels.append({"name": c.name, "x": round(ax, 1), "y": round(ay, 1), "r": round(r, 1)})
    placed = [proj(p["lon"], p["lat"]) for _, p, _ in pts]
    event_countries = {p["country"] for _, p, _ in pts}
    for lab in labels:                                  # a country holding an event is always named
        lab["key"] = lab["name"] in event_countries

    layers = layers if layers is not None else default_layers()
    lon_span = e - w
    rivers = [{"d": d} for lines in rivers_in_frame(layers, lon_span)
              if (d := line_path([cl for ln in lines for cl in clip_line([proj(x, y) for x, y in ln], box)], tol))]
    lakes = []
    for poly in layers.lakes:
        for drawn in _drawn([poly], _bounds([poly[0]]), frame, proj, box):
            if d := ring_path(drawn, tol, min_extent=max(4.0, 3 * tol)):
                lakes.append({"d": d})
    disputed = top_areas([ent for a in layers.disputed
                          if (polys := _drawn(a.polygons, a.bbox, frame, proj, box)) and (ent := disputed_entry(a, polys, tol))])
    cities = select_cities(layers, proj, frame, MAP_WIDTH, height, lon_span, event_countries)
    notes = chokepoint_notes(frame, proj, [(p["lon"], p["lat"]) for _, p, _ in pts], lon_span, as_of)

    points = []
    for (n_, place, dev), (x, y) in zip(pts, placed, strict=True):
        points.append({"x": round(x, 1), "y": round(y, 1), "label": place["name"], "date": dev.get("when", ""),
                       "verification": dev.get("verification", "reported"), "n": n_})
    credit = CREDIT + (" Disputed areas: Natural Earth (public domain)." if disputed else "") + (" Shipping data: IMF PortWatch." if notes else "") \
        + (f" Not on this map (too far away): {', '.join(elsewhere)}." if elsewhere else "")
    return {"version": 2, "bbox": [round(w, 3), round(s, 3), round(e, 3), round(n, 3)],
            "projection": "equirectangular", "width": MAP_WIDTH, "height": height, "countries": land,
            "labels": labels, "rivers": rivers, "lakes": lakes, "disputed": disputed, "cities": cities, "annotations": notes,
            "scale": scale_bar(w, e, (s + n) / 2, MAP_WIDTH), "locator": _locator(countries, frame),
            "points": points, "credit": credit}
