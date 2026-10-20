"""
Derivation — aircraft records to per-cell (observations, degraded) tallies. Pure: no I/O.

An observation is one aircraft in one hourly sample. It counts only if it is airborne, its position came from ADS-B itself (not multilateration or
a rebroadcast) and its transponder is version 2 (the only one that reports NACp). It is degraded when NACp is below ``DEGRADED_NACP``.
"""

from __future__ import annotations

import math
from collections.abc import Iterable
from typing import Any

from . import flags

Tally = dict[str, list[int]]                        # cell -> [observations, degraded]


def cell_of(lat: float, lon: float) -> str:
    d = flags.CELL_DEG
    return f"{math.floor(lat / d) * d:g},{math.floor(lon / d) * d:g}"


def cell_center(cell: str) -> tuple[float, float]:
    la, lo = (float(x) for x in cell.split(","))
    return la + flags.CELL_DEG / 2, lo + flags.CELL_DEG / 2


def usable(ac: dict[str, Any]) -> bool:
    """An airborne, ADS-B-positioned, version-2 aircraft with a position and a NACp."""
    return (isinstance(ac.get("lat"), (int, float)) and isinstance(ac.get("lon"), (int, float)) and isinstance(ac.get("nac_p"), int)
            and str(ac.get("type", "")).startswith("adsb") and ac.get("version", 0) >= 2 and ac.get("alt_baro") != "ground")


def tally(aircraft: Iterable[dict[str, Any]]) -> Tally:
    """Per-cell [observations, degraded] over distinct aircraft (by ICAO hex; the first record seen wins when sample circles overlap)."""
    seen: set[str] = set()
    out: Tally = {}
    for ac in aircraft:
        hexid = str(ac.get("hex", ""))
        if not usable(ac) or (hexid and hexid in seen):
            continue
        seen.add(hexid)
        row = out.setdefault(cell_of(ac["lat"], ac["lon"]), [0, 0])
        row[0] += 1
        row[1] += ac["nac_p"] < flags.DEGRADED_NACP
    return out
