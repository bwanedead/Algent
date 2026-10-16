"""
Where memory looks — the 1-degree grid, the named areas, and the vocabulary of series (pure data and arithmetic; no I/O).

A PLACE is one of: a 1-degree cell (an ``int`` id, ``row * 360 + column`` with ``row = floor(lat) + 90``, the same ids as the
AIS receiver-coverage layer), a named area (``"gate:hormuz"``, ``"region:black_sea"``, ``"fire:ukraine_front"``; the boxes of
``live/regions.py``, so the chokepoints, aircraft regions and fire-watch boxes the rest of /live already uses) or the whole
world (``"w"``). A SERIES is ``"<layer>.<class>"``: ``ship.tanker``, ``air.military``, ``fire.count`` ...
"""

from __future__ import annotations

import math
from typing import NamedTuple

from ..regions import FIRE_BOXES, GATES, REGIONS, BBox, inside

WORLD = "w"

#: Classes of each layer. Ship classes follow ``classify.VESSEL_CLASSES``; aircraft ``support`` (tankers and surveillance) is a
#: SUBSET of ``military``. ``heard`` is not a class but the receiver-coverage reading (see sampler); ``all`` is the sum of the
#: partition (areas and the world only; cells derive it).
CLASSES: dict[str, tuple[str, ...]] = {
    "ship": ("tanker", "cargo", "passenger", "fishing", "military", "other"),
    "air": ("civil", "military", "support"),
    "fire": ("count", "frp"),
}
#: The classes that add up to the layer's total (``support`` is inside ``military``).
PARTITION: dict[str, tuple[str, ...]] = {"ship": CLASSES["ship"], "air": ("civil", "military")}
#: Layers that are judged for anomalies (quakes and outages are only counted).
SCORED = ("ship", "air", "fire")

PHRASE: dict[str, str] = {
    "ship.tanker": "tankers", "ship.cargo": "cargo ships", "ship.passenger": "passenger ships", "ship.fishing": "fishing vessels",
    "ship.military": "military and law-enforcement ships", "ship.other": "other ships",
    "air.civil": "civil aircraft", "air.military": "military aircraft", "air.support": "tanker and surveillance aircraft",
    "fire.count": "satellite fire detections", "fire.frp": "fire intensity",
}


def series_of(layer: str, klass: str) -> str:
    return f"{layer}.{klass}"


def layer_of(series: str) -> str:
    return series.split(".", 1)[0]


class Area(NamedTuple):
    id: str
    kind: str                       # gate | region | fire
    slug: str
    label: str
    box: BBox
    tags: tuple[str, ...]
    countries: tuple[str, ...]


def _areas() -> tuple[Area, ...]:
    out = [Area(f"gate:{g.slug}", "gate", g.slug, g.label, g.box, g.tags, g.countries) for g in GATES]
    out += [Area(f"region:{r.slug}", "region", r.slug, r.label, r.box, r.tags, r.countries) for r in REGIONS]
    out += [Area(f"fire:{b.slug}", "fire", b.slug, b.label, b.box, b.tags, b.countries) for b in FIRE_BOXES]
    return tuple(out)


AREAS: tuple[Area, ...] = _areas()
BY_ID: dict[str, Area] = {a.id: a for a in AREAS}


# ── the grid ────────────────────────────────────────────────────────────────────────────────────
def cell_of(lat: float, lon: float) -> int:
    return int(math.floor(lat + 90)) * 360 + int(math.floor(lon + 180))


def cell_center(cell: int) -> tuple[float, float]:
    """(lat, lon) of the middle of a cell."""
    return cell // 360 - 90 + 0.5, cell % 360 - 180 + 0.5


def cells_of(box: BBox) -> tuple[int, ...]:
    """Every cell the box overlaps."""
    south, west, north, east = box
    return tuple(r * 360 + c for r in range(int(math.floor(south + 90)), int(math.floor(north + 90)) + 1)
                 for c in range(int(math.floor(west + 180)), int(math.floor(east + 180)) + 1))


AREA_CELLS: dict[str, tuple[int, ...]] = {a.id: cells_of(a.box) for a in AREAS}
_BY_CELL: dict[int, tuple[Area, ...]] = {}
for _a in AREAS:
    for _c in AREA_CELLS[_a.id]:
        _BY_CELL[_c] = (*_BY_CELL.get(_c, ()), _a)


def areas_at(lat: float, lon: float) -> tuple[Area, ...]:
    """The named areas whose box contains the point (cheap: only the areas overlapping the point's cell are tested)."""
    return tuple(a for a in _BY_CELL.get(cell_of(lat, lon), ()) if inside(a.box, lat, lon))


def hemisphere(lat: float, lon: float) -> str:
    return f"{abs(lat):.0f}°{'N' if lat >= 0 else 'S'} {abs(lon):.0f}°{'E' if lon >= 0 else 'W'}"


def place_label(place: int | str) -> str:
    if isinstance(place, int):
        lat, lon = cell_center(place)
        return f"near {hemisphere(lat, lon)}"
    return "the world" if place == WORLD else BY_ID[place].label if place in BY_ID else place


def place_kind(place: int | str) -> str:
    return "cell" if isinstance(place, int) else "world" if place == WORLD else BY_ID[place].kind if place in BY_ID else "area"


def place_lonlat(place: int | str) -> tuple[float, float] | None:
    """(lat, lon): a cell's middle, an area's box centre; None for the world."""
    if isinstance(place, int):
        return cell_center(place)
    if place in BY_ID:
        b = BY_ID[place].box
        return round((b[0] + b[2]) / 2, 3), round((b[1] + b[3]) / 2, 3)
    return None


def place_countries(place: int | str) -> list[str]:
    """Countries the place speaks to: an area's own; a cell's = those of the areas containing its middle."""
    if isinstance(place, str):
        return list(BY_ID[place].countries) if place in BY_ID else []
    lat, lon = cell_center(place)
    return sorted({c for a in areas_at(lat, lon) for c in a.countries})


def place_tags(place: int | str) -> list[str]:
    if isinstance(place, str):
        return list(BY_ID[place].tags) if place in BY_ID else []
    lat, lon = cell_center(place)
    return sorted({t for a in areas_at(lat, lon) for t in a.tags})


# ── daily rollup series (the `live_mem_*` instrument series) ─────────────────────────────────────
#: name -> (series, human noun). The mean number present across the UTC day's observed hours.
DAILY: dict[str, tuple[str, str]] = {
    "ships": ("ship.all", "ships"), "tankers": ("ship.tanker", "tankers"), "navy": ("ship.military", "military and law-enforcement ships"),
    "mil_air": ("air.military", "military aircraft"),
}
#: Which daily series each kind of area gets (chokepoints are ship lanes; aircraft regions also watch the sky).
DAILY_FOR: dict[str, tuple[str, ...]] = {"gate": ("ships", "tankers", "navy"), "region": ("ships", "tankers", "navy", "mil_air")}


def daily_id(area: Area, name: str) -> str:
    return f"live_mem_{area.kind}_{area.slug}_{name}"


def daily_series() -> list[tuple[str, Area, str]]:
    """(instrument series id, area, daily name) for every rollup series."""
    return [(daily_id(a, n), a, n) for a in AREAS for n in DAILY_FOR.get(a.kind, ())]
