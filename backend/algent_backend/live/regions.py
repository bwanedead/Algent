"""
Where we listen — chokepoint gates, aircraft regions and fire-watch boxes, as plain data (no I/O).

Gates and boxes are approximate hand-set geometry (about 10 km), chosen at the narrowest point of each passage.
A GATE is a line segment ``a -> b`` (lat, lon) inside a bounding box: a vessel counts as one transit when two
successive positions of the same MMSI fall on opposite sides of the segment, inside the box. Tags are the same
vocabulary the instruments catalog uses (``hormuz``, ``red-sea`` ...), which is what lets a theater find these
counts. ``countries`` are the names the desk matches events against (a theater's own text), so a theater about
the Black Sea finds the Black Sea aircraft.
"""

from __future__ import annotations

from typing import NamedTuple

BBox = tuple[float, float, float, float]          # (south, west, north, east) — lat/lon order, like AIS APIs


class Gate(NamedTuple):
    slug: str
    label: str
    box: BBox
    a: tuple[float, float]                         # (lat, lon) ends of the counting line
    b: tuple[float, float]
    tags: tuple[str, ...]
    countries: tuple[str, ...]
    portwatch: str = ""                            # the IMF PortWatch reference series this count sits beside


GATES: tuple[Gate, ...] = (
    Gate("hormuz", "Strait of Hormuz", (25.8, 55.6, 27.2, 57.2), (25.9, 56.45), (27.0, 56.45),
         ("hormuz", "iran", "gulf", "oil", "energy"), ("Iran", "Oman", "United Arab Emirates"), "chk_hormuz_transits"),
    Gate("bab_el_mandeb", "Bab el-Mandeb", (12.0, 42.6, 13.2, 43.9), (12.6, 42.6), (12.6, 43.9),
         ("bab-el-mandeb", "red-sea", "yemen", "houthi"), ("Yemen", "Djibouti", "Eritrea"), "chk_bab_el_mandeb_transits"),
    Gate("suez", "Suez Canal", (29.8, 32.2, 31.4, 32.8), (30.0, 32.2), (30.0, 32.8),
         ("suez", "egypt", "red-sea"), ("Egypt",), "chk_suez_transits"),
    Gate("bosporus", "Bosporus", (40.9, 28.9, 41.3, 29.3), (41.1, 28.9), (41.1, 29.3),
         ("bosporus", "turkey", "black-sea", "russia", "ukraine"), ("Turkey",), "chk_bosporus_transits"),
    Gate("malacca", "Strait of Malacca", (1.8, 100.4, 3.2, 102.0), (2.5, 100.4), (2.5, 102.0),
         ("malacca", "asia", "china", "singapore"), ("Malaysia", "Indonesia", "Singapore"), "chk_malacca_transits"),
    Gate("taiwan_strait", "Taiwan Strait", (23.8, 117.5, 25.4, 120.8), (24.5, 117.5), (24.5, 120.8),
         ("taiwan-strait", "taiwan", "china", "asia"), ("Taiwan", "China"), ""),
)


class Region(NamedTuple):
    slug: str
    label: str
    box: BBox
    tags: tuple[str, ...]
    countries: tuple[str, ...]


REGIONS: tuple[Region, ...] = (
    Region("black_sea", "Black Sea", (40.5, 27.0, 47.5, 41.8), ("black-sea", "ukraine", "russia"), ("Ukraine", "Russia", "Turkey")),
    Region("persian_gulf", "Persian Gulf and Hormuz", (23.5, 47.0, 30.5, 60.0), ("gulf", "hormuz", "iran"),
           ("Iran", "Saudi Arabia", "Oman", "United Arab Emirates")),
    Region("taiwan_strait", "Taiwan Strait", (21.5, 116.0, 26.5, 123.5), ("taiwan-strait", "taiwan", "china"), ("Taiwan", "China")),
    Region("baltic", "Baltic Sea", (53.5, 9.0, 60.5, 30.0), ("baltic", "russia", "europe"),
           ("Russia", "Poland", "Sweden", "Finland", "Estonia", "Latvia", "Lithuania")),
    Region("east_med", "Eastern Mediterranean", (30.0, 28.0, 37.5, 36.5), ("east-med", "israel", "lebanon", "syria"),
           ("Israel", "Lebanon", "Syria", "Turkey", "Cyprus")),
    Region("red_sea", "Red Sea", (12.0, 32.0, 28.0, 44.0), ("red-sea", "yemen", "houthi"),
           ("Yemen", "Egypt", "Saudi Arabia", "Eritrea", "Sudan")),
)


class FireBox(NamedTuple):
    slug: str
    label: str
    box: BBox
    tags: tuple[str, ...]
    countries: tuple[str, ...]


#: Where a thermal hotspot is news: front lines and the refinery belt. A hotspot is a heat reading from a
#: satellite; it can be a wildfire, an industrial flare or a strike, and the data alone does not say which.
FIRE_BOXES: tuple[FireBox, ...] = (
    FireBox("ukraine_front", "Eastern Ukraine front", (46.0, 34.5, 50.0, 40.0), ("ukraine", "russia"), ("Ukraine", "Russia")),
    FireBox("russia_refineries_south", "Southern Russia refinery belt", (44.5, 38.0, 51.0, 48.5),
            ("russia", "oil", "energy", "ukraine"), ("Russia",)),
    FireBox("russia_refineries_volga", "Volga and central refineries", (52.0, 38.0, 57.5, 51.0), ("russia", "oil", "energy"), ("Russia",)),
    FireBox("gaza_levant", "Gaza and Lebanon border", (30.8, 34.0, 34.0, 36.0), ("israel", "gaza", "lebanon"), ("Israel", "Lebanon")),
)

#: Aircraft type designators (ICAO, as adsb.lol reports them) by role. Anything else counts as "other".
TANKERS = frozenset({"K35R", "KC10", "KC46", "A332", "K35T", "IL78"})
SURVEILLANCE = frozenset({"R135", "E3TF", "E3CF", "E3", "E6", "E8", "E7", "P8", "P3", "U2", "Q4", "RQ4", "MQ9", "MQ4",
                          "E2", "E2C", "A50", "IL20"})
AIRLIFT = frozenset({"C17", "C5M", "C5", "C30J", "C130", "A400", "IL76", "A124"})


FIGHTERS = frozenset({"F16", "F15", "F18", "F18S", "FA18", "F35", "F22", "EUFI", "RFAL", "GR4", "TORN", "F14", "SU27", "SU30",
                      "SU34", "SU35", "MG29", "M346", "A10", "B52", "B1", "B2", "TU95", "TU22", "TU160"})

#: Where civil traffic is swept (lat, lon); radius is the API maximum (250 nautical miles). Each cycle polls the next few (flags.CIVIL_POLLS_PER_CYCLE).
CIVIL_HUBS: tuple[tuple[float, float], ...] = (
    (51.0, 2.0), (48.5, 11.0), (41.0, 13.0), (40.0, -4.0), (41.0, 29.0), (31.0, 34.0), (25.2, 55.3), (28.5, 77.0),
    (19.0, 73.0), (13.7, 100.7), (1.4, 103.8), (22.3, 114.1), (31.2, 121.5), (39.9, 116.4), (35.6, 139.7), (37.5, 127.0),
    (40.6, -73.8), (41.9, -87.9), (33.9, -84.4), (32.9, -97.0), (34.0, -118.4), (47.5, -122.3), (19.4, -99.1), (-23.5, -46.6),
    (-34.8, -58.5), (4.7, -74.1), (-26.1, 28.2), (30.1, 31.4), (6.6, 3.3), (-1.3, 36.9), (-33.9, 151.2), (-37.7, 144.8),
    (64.0, -22.0), (60.0, 11.0), (55.7, 37.6), (50.4, 30.5),
    (39.9, -104.7), (33.4, -112.0), (25.8, -80.3), (44.9, -93.2), (42.4, -71.0),
)


def aircraft_class(type_code: str, is_mil: bool) -> int:
    """0 civil, 1 other military, 2 tanker, 3 surveillance, 4 airlift, 5 fighter or bomber (type codes as adsb.lol reports them)."""
    if not is_mil:
        return 0
    t = (type_code or "").upper()
    return 2 if t in TANKERS else 3 if t in SURVEILLANCE else 4 if t in AIRLIFT else 5 if t in FIGHTERS else 1


def role_of(type_code: str) -> str:
    t = (type_code or "").upper()
    return "tanker" if t in TANKERS else "surveillance" if t in SURVEILLANCE else "airlift" if t in AIRLIFT else "other"


def inside(box: BBox, lat: float, lon: float) -> bool:
    return box[0] <= lat <= box[2] and box[1] <= lon <= box[3]
