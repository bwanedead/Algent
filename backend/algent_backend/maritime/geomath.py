"""Small geometry for the maritime detectors (pure arithmetic; no I/O)."""

from __future__ import annotations

import math

_R_KM = 6371.0088


def km_between(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """Great-circle distance in kilometres (haversine)."""
    p1, p2 = math.radians(lat1), math.radians(lat2)
    a = math.sin((p2 - p1) / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(math.radians(lon2 - lon1) / 2) ** 2
    return 2 * _R_KM * math.asin(min(1.0, math.sqrt(a)))


def offset(lat: float, lon: float, km: float, bearing_deg: float) -> tuple[float, float]:
    """The point ``km`` away from (lat, lon) on a bearing (flat-earth: exact enough for a few kilometres)."""
    dlat = km * math.cos(math.radians(bearing_deg)) / 111.195
    dlon = km * math.sin(math.radians(bearing_deg)) / (111.195 * max(0.05, math.cos(math.radians(lat))))
    return lat + dlat, lon + dlon


def cell_id(lat: float, lon: float) -> int:
    """The 1-degree cell id the AIS coverage layer and live memory share: ``row * 360 + column``."""
    return int(math.floor(lat + 90)) * 360 + int(math.floor(lon + 180))


def block(lat: float, lon: float, deg: int = 1) -> list[int]:
    """Cell ids of the (2 * deg + 1)^2 block centred on the point's cell (longitude wraps, latitude is clipped)."""
    row, col = int(math.floor(lat + 90)), int(math.floor(lon + 180))
    return [rr * 360 + cc % 360 for rr in range(max(0, row - deg), min(179, row + deg) + 1) for cc in range(col - deg, col + deg + 1)]
