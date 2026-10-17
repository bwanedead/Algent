"""
Where behaviour is judged: the port / coast exclusion (open water vs port business) and the sensitive zones.

``Exclusion`` answers "is this position port business?": near a known port (geoledger ``port`` assets, when the ledger holds any) OR with
land within ``COAST_KM`` (probed on a ring of points against the Natural Earth basemap; no basemap, no coast layer - never a guess).
``ZONES`` are the places a slow, long dwell matters: the chokepoint boxes of ``live/regions.py`` and a few HAND-SET boxes around
undersea cable and pipeline corridors. The cable boxes are PROXIES (approximate corridors, not surveyed routes); replace them with a
cable-route dataset when one is available.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import NamedTuple

from algent_backend.live.regions import GATES, BBox, inside

from . import flags
from .geomath import km_between, offset


class Zone(NamedTuple):
    slug: str
    label: str
    kind: str                      # chokepoint | cable
    box: BBox                      # (south, west, north, east)
    countries: tuple[str, ...]     # the names the desk matches against a theater


_CABLE_PROXIES: tuple[Zone, ...] = (
    Zone("gulf_of_finland_cables", "Gulf of Finland cable and pipeline corridor (proxy)", "cable", (59.3, 23.5, 60.1, 25.3),
         ("Finland", "Estonia", "Russia")),
    Zone("southern_baltic_cables", "Bornholm and southern Baltic pipeline and cable area (proxy)", "cable", (54.9, 14.3, 55.6, 15.9),
         ("Denmark", "Sweden", "Poland", "Germany")),
    Zone("baltic_trunk_cables", "Central Baltic trunk cable route (proxy)", "cable", (56.5, 17.5, 59.0, 21.0),
         ("Sweden", "Finland", "Latvia", "Estonia")),
    Zone("taiwan_matsu_cables", "Taiwan to Matsu cable approaches (proxy)", "cable", (24.8, 119.3, 26.3, 121.8), ("Taiwan", "China")),
    Zone("red_sea_north_cables", "Northern Red Sea cable landings near Zafarana (proxy)", "cable", (28.4, 32.4, 29.8, 33.6), ("Egypt",)),
    Zone("dover_cables", "Dover Strait cable bundle (proxy)", "cable", (50.6, 0.8, 51.4, 2.0), ("United Kingdom", "France")),
)
ZONES: tuple[Zone, ...] = (*(Zone(g.slug, g.label, "chokepoint", g.box, g.countries) for g in GATES), *_CABLE_PROXIES)


def zone_at(lat: float, lon: float) -> Zone | None:
    return next((z for z in ZONES if inside(z.box, lat, lon)), None)


class Exclusion:
    """Port / coast proximity with the data injected so tests need neither a ledger nor a basemap."""

    def __init__(self, ports: list[tuple[float, float]] | None = None, is_land: Callable[[float, float], bool] | None = None) -> None:
        self.ports: dict[tuple[int, int], list[tuple[float, float]]] = {}
        for lat, lon in ports or []:
            self.ports.setdefault((int(lat), int(lon)), []).append((lat, lon))
        self.is_land = is_land
        self._coast: dict[tuple[int, int], bool] = {}

    def near_port(self, lat: float, lon: float) -> bool:
        if not self.ports:
            return False
        r, c = int(lat), int(lon)
        return any(km_between(lat, lon, plat, plon) <= flags.PORT_KM
                   for dr in (-1, 0, 1) for dc in (-1, 0, 1) for plat, plon in self.ports.get((r + dr, c + dc), ()))

    def near_coast(self, lat: float, lon: float) -> bool:
        """Land within COAST_KM, probed on a ring (cached per ~5 km cell)."""
        if self.is_land is None:
            return False
        key = (round(lat * 20), round(lon * 20))
        hit = self._coast.get(key)
        if hit is None:
            if len(self._coast) > 50000:
                self._coast.clear()
            hit = self.is_land(lat, lon) or any(self.is_land(*offset(lat, lon, flags.COAST_KM, 360 * i / flags.COAST_PROBES))
                                                for i in range(flags.COAST_PROBES))
            self._coast[key] = hit
        return hit

    def in_port_area(self, lat: float, lon: float) -> bool:
        return self.near_port(lat, lon) or self.near_coast(lat, lon)


def from_environment() -> Exclusion:
    """Ports from the geoledger and land from the basemap, each optional (a missing source narrows the exclusion, never raises)."""
    ports: list[tuple[float, float]] = []
    try:
        from algent_backend.geoledger.store import Ledger

        ports = [(a.lat, a.lon) for a in Ledger().live() if a.type == "port" and a.lat is not None and a.lon is not None]
    except Exception:  # noqa: BLE001
        ports = []
    is_land: Callable[[float, float], bool] | None = None
    try:
        from algent_backend.live import places

        if places._countries():
            is_land = lambda la, lo: places.country_at(la, lo) is not None  # noqa: E731
    except Exception:  # noqa: BLE001
        is_land = None
    return Exclusion(ports, is_land)
