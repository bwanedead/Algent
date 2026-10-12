"""
Live points — the world-zoom form of the vessel and aircraft snapshots.

The far-out /live map is a soft heat glow drawn from EVERY object's real position. This document carries exactly that and
nothing else: per layer, each object's position rounded to ``POINT_DEG`` (0.05 degree, about 5 km — under two pixels at the
last zoom where the heat shows) plus its class. No ids, names, headings or trails. ~30 KB gzipped for 26,000 ships and 7,000
aircraft; the full snapshot is ~0.95 MB. No thinning: duplicates are kept (a busy port IS several points on the same spot) so
the glow is the one the full document gives.

Layout of ``layers.<name>.p`` — a flat int array, three ints per point, points sorted south to north then west to east and
delta-coded (it gzips ~2x better than absolute values)::

    dlat, lon, c      dlat = lat step from the previous point in 0.05 degree units (>= 0);
                      lon  = absolute longitude (0.05 degree units) when dlat > 0, else the step from the previous point;
                      c    = class index + 8 when the object is "notable" (the map keeps notable objects when it thins a
                             huge layer, so the bit keeps that identical).

Pure functions of the two board documents; ``decode`` is the reference the site's decoder mirrors.
"""

from __future__ import annotations

from collections import Counter
from typing import Any

POINT_DEG = 0.05
_PER_DEG = round(1 / POINT_DEG)
_SOUTH = -90 * round(1 / POINT_DEG)         # deltas start at the south pole, so every latitude step is >= 0
NOTABLE_BIT = 8
TOP_FLAGS = 40
_LON, _LAT, _CLS, _FLAG, _NF = 1, 2, 5, 9, 10      # row positions (vessels; aircraft share lon/lat/cls)


def _notable(layer: str, row: list) -> bool:
    if layer == "vessels":
        return len(row) > _NF and bool(row[_NF])
    return int(row[_CLS]) > 0


def encode_points(doc: dict[str, Any], layer: str) -> list[int]:
    pts = sorted((round(r[_LAT] * _PER_DEG), round(r[_LON] * _PER_DEG), min(int(r[_CLS]), NOTABLE_BIT - 1) + (NOTABLE_BIT if _notable(layer, r) else 0))
                 for r in doc["rows"])
    out: list[int] = []
    prev_lat, prev_lon = _SOUTH, 0
    for lat, lon, c in pts:
        step = lat - prev_lat
        out += [step, lon - prev_lon if step == 0 else lon, c]
        prev_lat, prev_lon = lat, lon
    return out


def decode(flat: list[int]) -> list[tuple[float, float, int, bool]]:
    """``(lon, lat, class, notable)`` per point (positions on the 0.05 degree grid)."""
    out = []
    lat, lon = _SOUTH, 0
    for i in range(0, len(flat) - 2, 3):
        step, x, c = flat[i:i + 3]
        lat += step
        lon = lon + x if step == 0 else x
        out.append((lon / _PER_DEG, lat / _PER_DEG, c % NOTABLE_BIT, c >= NOTABLE_BIT))
    return out


def _layer(doc: dict[str, Any], name: str) -> dict[str, Any]:
    out: dict[str, Any] = {"n": doc["n"], "counts": doc.get("counts", {}), "classes": doc.get("classes", []), "p": encode_points(doc, name)}
    if name == "vessels":
        flags = Counter(r[_FLAG] for r in doc["rows"] if len(r) > _FLAG and r[_FLAG])
        out["flags"] = [[code, n] for code, n in flags.most_common(TOP_FLAGS)]
    return out


def build(vessels: dict[str, Any], aircraft: dict[str, Any]) -> dict[str, Any]:
    """The ``points`` document of one cycle."""
    return {"v": 1, "as_of": vessels["as_of"], "aircraft_as_of": aircraft["as_of"], "deg": POINT_DEG,
            "layers": {"vessels": _layer(vessels, "vessels"), "aircraft": _layer(aircraft, "aircraft")}}
