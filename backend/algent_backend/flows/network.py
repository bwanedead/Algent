"""
The lane network — the named places ships are watched in, and the sea lanes that join them (pure data and arithmetic; no I/O).

A PLACE is a box on the map: a chokepoint (the live gates' own boxes plus a few more) or a port region (the water and coast where a
trade's ships gather: the Persian Gulf, the US Gulf, Rotterdam's North Sea...). Every place has a centre in open water and a kind.
A LANE joins two neighbouring places and carries the waypoints that keep its drawn path on the sea (a hand-set polyline through
real straits and around real capes; approximate, about 100 km). A ship seen in one place and later in another has made a HOP;
``route`` turns any hop into the chain of lanes it must have sailed (the shortest sea path), so a ship the receivers lost over a
whole ocean still counts on the lanes it crossed, marked as inferred. Place boxes are generous because terrestrial AIS hears ships
only near volunteer stations; open ocean is simply not listened to.
"""

from __future__ import annotations

import heapq
import math
from functools import lru_cache
from typing import NamedTuple

from algent_backend.live.regions import GATES, BBox
from algent_backend.maritime.geomath import km_between

LatLon = tuple[float, float]


class Place(NamedTuple):
    id: str
    label: str
    kind: str                        # chokepoint | region
    lat: float                       # centre, in open water
    lon: float
    box: BBox                        # (south, west, north, east)


def _gate_places() -> list[Place]:
    out = []
    for g in GATES:
        out.append(Place(g.slug, g.label, "chokepoint", round((g.a[0] + g.b[0]) / 2, 3), round((g.a[1] + g.b[1]) / 2, 3), g.box))
    return out


def _cp(pid: str, label: str, lat: float, lon: float, box: BBox) -> Place:
    return Place(pid, label, "chokepoint", lat, lon, box)


def _rg(pid: str, label: str, lat: float, lon: float, box: BBox) -> Place:
    return Place(pid, label, "region", lat, lon, box)


#: Chokepoints first (a ship inside one is "in the strait", not in the region around it), then regions in a fixed order.
PLACES: tuple[Place, ...] = (
    *_gate_places(),
    _cp("panama", "Panama Canal", 9.1, -79.7, (8.6, -80.2, 9.6, -79.4)),
    _cp("gibraltar", "Strait of Gibraltar", 35.95, -5.6, (35.6, -6.2, 36.4, -5.0)),
    _cp("dover", "Dover Strait", 51.0, 1.5, (50.6, 0.6, 51.4, 2.0)),
    _cp("danish", "Danish straits", 55.6, 11.0, (54.6, 9.8, 57.8, 13.2)),
    _cp("dardanelles", "Dardanelles", 40.2, 26.4, (39.9, 26.0, 40.6, 27.0)),
    _cp("singapore", "Singapore Strait", 1.2, 103.8, (1.0, 103.3, 1.55, 104.5)),
    _cp("sunda", "Sunda Strait", -6.0, 105.8, (-6.6, 105.2, -5.6, 106.2)),
    _cp("lombok", "Lombok Strait", -8.6, 115.8, (-9.0, 115.4, -8.2, 116.2)),
    _rg("persian_gulf", "Persian Gulf", 27.0, 51.5, (24.0, 48.0, 30.4, 55.6)),
    _rg("gulf_of_oman", "Gulf of Oman", 24.5, 58.5, (22.0, 56.0, 25.9, 62.5)),
    _rg("india_west", "West coast of India", 20.0, 70.0, (14.0, 67.0, 24.5, 74.5)),
    _rg("sri_lanka", "Sri Lanka and south India", 7.5, 79.5, (5.5, 76.0, 14.0, 82.0)),
    _rg("bay_of_bengal", "Bay of Bengal", 16.0, 88.0, (14.0, 82.0, 23.0, 94.0)),
    _rg("gulf_of_aden", "Gulf of Aden", 12.5, 48.0, (11.0, 43.0, 15.5, 53.0)),
    _rg("red_sea", "Red Sea", 20.5, 38.5, (13.3, 34.0, 27.8, 43.0)),
    _rg("east_med", "Eastern Mediterranean", 33.5, 31.0, (31.0, 28.0, 37.0, 36.5)),
    _rg("central_med", "Central Mediterranean", 36.5, 14.0, (33.0, 9.0, 38.5, 20.0)),
    _rg("west_med", "Western Mediterranean", 40.0, 4.0, (36.0, -1.5, 44.0, 9.0)),
    _rg("adriatic", "Adriatic", 43.0, 15.5, (39.5, 12.0, 45.9, 20.0)),
    _rg("aegean", "Aegean", 38.5, 25.0, (35.0, 22.5, 40.6, 28.0)),
    _rg("black_sea", "Black Sea", 43.5, 34.0, (41.0, 27.5, 46.8, 41.9)),
    _rg("iberia_atlantic", "Atlantic Iberia", 39.0, -10.0, (36.0, -10.5, 43.8, -7.5)),
    _rg("english_channel", "Western English Channel", 49.5, -4.0, (48.0, -6.0, 50.6, 0.6)),
    _rg("north_sea_south", "Southern North Sea (Rotterdam, Antwerp)", 52.5, 3.5, (50.8, 1.5, 54.2, 8.5)),
    _rg("north_sea_north", "Northern North Sea", 58.0, 2.0, (54.2, -3.0, 62.0, 8.0)),
    _rg("baltic", "Baltic Sea", 57.5, 19.0, (53.5, 9.8, 60.5, 30.0)),
    _rg("us_gulf", "US Gulf coast", 27.5, -91.0, (25.5, -97.8, 30.6, -82.5)),
    _rg("us_east", "US East coast", 36.0, -74.0, (30.0, -81.5, 42.0, -69.5)),
    _rg("us_west", "US West coast", 34.0, -121.0, (32.3, -125.0, 49.5, -117.0)),
    _rg("caribbean", "Caribbean", 16.0, -72.0, (9.0, -84.0, 24.0, -60.0)),
    _rg("brazil_north", "Northern Brazil", -1.5, -44.0, (-5.0, -50.0, 2.0, -34.0)),
    _rg("brazil_southeast", "Southeast Brazil (Santos, Tubarao)", -23.5, -42.0, (-28.0, -49.0, -17.5, -37.5)),
    _rg("river_plate", "River Plate", -35.0, -56.0, (-39.0, -63.0, -31.5, -52.0)),
    _rg("west_africa", "West Africa", 3.0, 3.0, (-12.0, -2.0, 7.0, 14.0)),
    _rg("south_africa", "South Africa", -34.5, 22.0, (-35.5, 16.5, -26.0, 33.5)),
    _rg("east_africa", "East Africa", -6.0, 41.0, (-12.0, 38.5, -1.0, 44.0)),
    _rg("chile_peru", "Chile and Peru", -20.0, -71.5, (-35.0, -81.0, -4.0, -69.5)),
    _rg("south_china_sea", "South China Sea", 12.0, 112.0, (5.0, 104.5, 21.0, 121.5)),
    _rg("hong_kong", "Pearl River (Hong Kong, Shenzhen)", 21.8, 114.0, (21.0, 112.0, 23.5, 115.5)),
    _rg("east_china", "East China (Shanghai, Ningbo)", 30.0, 123.0, (27.0, 119.5, 33.0, 124.5)),
    _rg("yellow_sea", "Yellow Sea (Qingdao, Tianjin, Dalian)", 38.0, 122.5, (33.0, 118.0, 41.0, 127.0)),
    _rg("korea_japan", "Korea and Japan", 34.0, 130.0, (32.5, 127.5, 36.5, 141.5)),
    _rg("indonesia", "Java Sea and Borneo", -5.0, 111.0, (-8.5, 105.5, 1.0, 119.0)),
    _rg("australia_west", "Western Australia (Port Hedland)", -20.0, 115.0, (-24.5, 112.0, -14.0, 122.5)),
    _rg("australia_east", "Eastern Australia (Newcastle, Gladstone)", -28.0, 154.0, (-34.5, 149.0, -22.0, 154.5)),
)
BY_ID: dict[str, Place] = {p.id: p for p in PLACES}

#: (a, b, waypoints between the two centres). Undirected; a ship sails either way.
LANES: tuple[tuple[str, str, tuple[LatLon, ...]], ...] = (
    ("persian_gulf", "hormuz", ()),
    ("hormuz", "gulf_of_oman", ()),
    ("gulf_of_oman", "india_west", ((21.5, 64.0),)),
    ("gulf_of_oman", "gulf_of_aden", ((19.0, 60.5), (14.0, 54.0))),
    ("india_west", "gulf_of_aden", ((15.5, 62.0), (13.2, 54.5))),
    ("gulf_of_aden", "bab_el_mandeb", ()),
    ("bab_el_mandeb", "red_sea", ((16.5, 40.5),)),
    ("red_sea", "suez", ((27.5, 34.3), (29.0, 32.8))),
    ("suez", "east_med", ((31.6, 32.4),)),
    ("east_med", "central_med", ((34.2, 26.0), (35.2, 20.5))),
    ("east_med", "aegean", ((35.5, 27.5),)),
    ("aegean", "dardanelles", ()),
    ("dardanelles", "bosporus", ((40.7, 28.2),)),
    ("bosporus", "black_sea", ()),
    ("central_med", "aegean", ((34.5, 22.0), (34.7, 26.5), (36.5, 27.0))),
    ("central_med", "adriatic", ((38.3, 18.0), (40.0, 18.9))),
    ("central_med", "west_med", ((37.3, 11.2), (38.2, 7.0))),
    ("west_med", "gibraltar", ((38.0, 0.0), (36.5, -2.5))),
    ("gibraltar", "iberia_atlantic", ((36.0, -8.0),)),
    ("iberia_atlantic", "english_channel", ((43.5, -9.8), (46.5, -6.0))),
    ("english_channel", "dover", ()),
    ("dover", "north_sea_south", ((52.0, 2.5),)),
    ("north_sea_south", "north_sea_north", ((54.5, 3.5),)),
    ("north_sea_south", "danish", ((54.0, 7.0), (56.0, 7.5), (58.0, 9.5))),
    ("danish", "baltic", ((55.0, 13.5),)),
    ("english_channel", "us_east", ((49.0, -12.0), (46.0, -35.0), (41.5, -60.0))),
    ("iberia_atlantic", "us_east", ((38.0, -25.0), (37.0, -55.0))),
    ("north_sea_north", "us_east", ((60.0, -15.0), (52.0, -45.0), (43.0, -62.0))),
    ("us_east", "us_gulf", ((31.0, -79.0), (25.5, -79.3), (24.0, -81.5), (24.5, -85.0))),
    ("us_east", "caribbean", ((27.0, -72.0), (21.5, -68.0))),
    ("us_gulf", "caribbean", ((26.0, -88.0), (22.0, -85.5))),
    ("caribbean", "panama", ((10.5, -77.0),)),
    ("panama", "us_west", ((7.0, -80.5), (12.0, -92.0), (18.5, -106.0), (24.0, -113.5))),
    ("panama", "chile_peru", ((6.5, -81.5), (-4.0, -82.5))),
    ("caribbean", "brazil_north", ((9.5, -58.0), (5.5, -50.0))),
    ("brazil_north", "brazil_southeast", ((0.0, -39.0), (-4.0, -33.5), (-10.0, -34.0), (-17.5, -36.5))),
    ("brazil_southeast", "river_plate", ((-29.0, -46.5), (-34.0, -52.0))),
    ("brazil_southeast", "south_africa", ((-28.0, -30.0), (-34.0, 0.0))),
    ("river_plate", "south_africa", ((-36.5, -50.0), (-38.0, -30.0), (-37.0, -5.0))),
    ("brazil_southeast", "west_africa", ((-18.0, -30.0), (-8.0, -5.0))),
    ("west_africa", "south_africa", ((-4.0, 5.0), (-15.0, 8.0), (-28.0, 12.0))),
    ("west_africa", "iberia_atlantic", ((0.5, -5.0), (10.0, -19.5), (22.0, -19.0), (33.0, -11.5))),
    ("west_africa", "caribbean", ((5.0, -30.0), (10.0, -50.0))),
    ("south_africa", "east_africa", ((-31.0, 33.0), (-25.5, 36.5), (-17.0, 41.5))),
    ("east_africa", "gulf_of_aden", ((-1.0, 44.0), (5.0, 50.0), (11.8, 51.5))),
    ("east_africa", "india_west", ((-2.0, 47.0), (10.0, 60.0))),
    ("south_africa", "sri_lanka", ((-36.0, 40.0), (-35.0, 65.0), (-15.0, 82.0))),
    ("south_africa", "australia_west", ((-37.5, 45.0), (-37.0, 80.0), (-31.0, 108.0))),
    ("sri_lanka", "india_west", ((7.0, 76.5),)),
    ("sri_lanka", "bay_of_bengal", ((8.0, 83.0),)),
    ("sri_lanka", "malacca", ((5.5, 86.0), (5.5, 92.0), (5.5, 96.5), (4.0, 99.5))),
    ("bay_of_bengal", "malacca", ((10.0, 92.5), (6.5, 96.5), (4.0, 99.5))),
    ("malacca", "singapore", ((1.9, 102.8),)),
    ("singapore", "south_china_sea", ((1.4, 104.7), (3.0, 107.0))),
    ("singapore", "indonesia", ((-0.5, 105.0), (-3.0, 107.5))),
    ("indonesia", "sunda", ((-5.5, 108.0), (-5.8, 106.2))),
    ("sunda", "australia_west", ((-12.0, 106.0), (-18.5, 111.5))),
    ("indonesia", "lombok", ((-6.5, 114.5),)),
    ("lombok", "australia_west", ((-12.0, 116.0),)),
    ("lombok", "south_china_sea", ((-5.5, 117.5), (0.0, 119.0), (7.0, 118.5))),
    ("south_china_sea", "hong_kong", ((17.0, 114.0),)),
    ("south_china_sea", "taiwan_strait", ((18.0, 117.5), (22.0, 119.0))),
    ("hong_kong", "taiwan_strait", ((22.2, 116.0),)),
    ("taiwan_strait", "east_china", ((26.5, 121.0),)),
    ("east_china", "yellow_sea", ((33.0, 123.5), (36.0, 123.5))),
    ("yellow_sea", "korea_japan", ((35.0, 123.8), (33.2, 126.5))),
    ("east_china", "korea_japan", ((31.5, 127.5),)),
    ("korea_japan", "us_west", ((40.0, 150.0), (46.0, -170.0), (45.0, -140.0))),
    ("australia_east", "korea_japan", ((-20.0, 157.0), (0.0, 152.0), (20.0, 145.0))),
    ("australia_east", "east_china", ((-20.0, 157.0), (5.0, 145.0), (22.0, 128.0))),
    ("australia_east", "lombok", ((-18.0, 152.0), (-11.0, 143.5), (-9.5, 132.0))),
)

# ── lookup: which place is a point in ────────────────────────────────────────────────────────────
_GRID: dict[tuple[int, int], list[Place]] = {}


def _build_grid() -> None:
    for p in PLACES:                                   # PLACES order is the priority order
        s, w, n, e = p.box
        for r in range(math.floor(s), math.floor(n) + 1):
            for c in range(math.floor(w), math.floor(e) + 1):
                _GRID.setdefault((r, c), []).append(p)


_build_grid()


def place_at(lat: float, lon: float) -> str | None:
    """Id of the first place (chokepoints before regions) whose box holds the point, or None in open water."""
    for p in _GRID.get((math.floor(lat), math.floor(lon)), ()):
        s, w, n, e = p.box
        if s <= lat <= n and w <= lon <= e:
            return p.id
    return None


# ── the graph and its routes ─────────────────────────────────────────────────────────────────────
def _polyline(a: str, b: str, via: tuple[LatLon, ...]) -> list[LatLon]:
    pa, pb = BY_ID[a], BY_ID[b]
    return [(pa.lat, pa.lon), *via, (pb.lat, pb.lon)]


def length_km(line: list[LatLon]) -> float:
    return sum(km_between(*line[i], *line[i + 1]) for i in range(len(line) - 1))


_LINES: dict[tuple[str, str], list[LatLon]] = {}
_ADJ: dict[str, list[tuple[str, float]]] = {p.id: [] for p in PLACES}
for _a, _b, _via in LANES:
    _line = _polyline(_a, _b, _via)
    _km = length_km(_line)
    _LINES[(_a, _b)], _LINES[(_b, _a)] = _line, _line[::-1]
    _ADJ[_a].append((_b, _km))
    _ADJ[_b].append((_a, _km))


def is_lane(a: str, b: str) -> bool:
    return (a, b) in _LINES


def lane_line(a: str, b: str) -> list[LatLon]:
    """The drawn path of the lane from ``a`` to ``b`` (centre, waypoints, centre), oriented a -> b."""
    return _LINES[(a, b)]


@lru_cache(maxsize=4096)
def route(a: str, b: str) -> tuple[tuple[str, ...], float] | None:
    """The shortest sea path from place ``a`` to place ``b`` as (the places along it, kilometres), or None when not connected."""
    if a not in _ADJ or b not in _ADJ:
        return None
    best: dict[str, float] = {a: 0.0}
    prev: dict[str, str] = {}
    heap: list[tuple[float, str]] = [(0.0, a)]
    while heap:
        d, u = heapq.heappop(heap)
        if u == b:
            break
        if d > best.get(u, math.inf):
            continue
        for v, w in _ADJ[u]:
            nd = d + w
            if nd < best.get(v, math.inf):
                best[v], prev[v] = nd, u
                heapq.heappush(heap, (nd, v))
    if b not in best:
        return None
    path = [b]
    while path[-1] != a:
        path.append(prev[path[-1]])
    return tuple(reversed(path)), best[b]
