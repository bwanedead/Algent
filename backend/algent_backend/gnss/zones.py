"""
Zones — a day's per-cell tally to scored interference zones, with a baseline-aware flag.

A cell is a zone when it holds enough observations and its degraded share is above background. Its flag compares today with that cell's OWN history
using live memory's robust statistics (``live/memory/robust.py``: median, MAD, modified z-score, ``Z_ENTER``): a cell that was always quiet and now is
not is ``new``; a cell that was already elevated and now stands out from its own normal is ``intensifying``. Until ``FLAG_AFTER_DAYS`` closed days
exist nothing is flagged (the baseline is still forming) and every zone says since when we have been watching.
"""

from __future__ import annotations

from collections.abc import Callable
from datetime import date

from algent_backend.live.memory import flags as memory_flags
from algent_backend.live.memory import robust

from . import flags, store
from .contracts import COVERAGE, Zone, zone_id
from .derive import Tally, cell_center


def severity(share: float) -> str:
    return "high" if share >= flags.HIGH_SHARE else "medium" if share >= flags.MEDIUM_SHARE else "low"


def history(cell: str, day: str, today: date) -> list[float]:
    """The cell's share (in percent) on each earlier day it was observed enough to score."""
    out = []
    for d in store.prior_days(day, flags.HISTORY_DAYS):
        n, bad = store.day_tally(d, today).get(cell, (0, 0))
        if n >= flags.MIN_OBSERVATIONS:
            out.append(100.0 * bad / n)
    return out


def flag_for(share: float, hist: list[float]) -> str:
    """'' | 'new' | 'intensifying' for today's share (0..1) against the cell's earlier shares (percent)."""
    if share < flags.ENTER_SHARE or len(hist) < flags.MIN_CELL_DAYS:
        return ""
    normal = robust.normal_of(hist)
    if normal is None:
        return ""
    if normal.median < 100.0 * flags.MIN_SHARE:
        return "new"
    return "intensifying" if robust.score(100.0 * share, normal) >= memory_flags.Z_ENTER else ""


def country_of(lat: float, lon: float) -> str:
    """ISO2 of the land under a point, "" at sea or without the basemap."""
    try:
        from algent_backend.actors import registry
        from algent_backend.live import places

        name = places.country_at(lat, lon)
        return (registry.resolve(name) or "") if name else ""
    except Exception:  # noqa: BLE001 - a missing basemap must never stop the pass
        return ""


def build(day: str, *, today: date | None = None, tally: Tally | None = None,
          country: Callable[[float, float], str] = country_of) -> list[Zone]:
    """The day's zones, most severe first."""
    today = today or date.today()
    tally = tally if tally is not None else store.day_tally(day, today)
    mature = store.baseline_days(today) >= flags.FLAG_AFTER_DAYS
    since = store.since().get("ohmega_adsb", "")
    out = []
    for cell, (n, bad) in tally.items():
        share = bad / n if n else 0.0
        if n < flags.MIN_OBSERVATIONS or share < flags.MIN_SHARE or bad < flags.MIN_DEGRADED:
            continue
        lat, lon = cell_center(cell)
        out.append(Zone(
            id=zone_id("ohmega_adsb", day, cell), date=day, source="ohmega_adsb", cell=cell, lat=lat, lon=lon, size_deg=flags.CELL_DEG,
            country=country(lat, lon), severity=severity(share), degraded_share=round(share, 4), aircraft=n,
            flag=flag_for(share, history(cell, day, today)) if mature else "", basis="our_estimate",
            coverage_note=COVERAGE["ohmega_adsb"], baseline_since=since))
    return sorted(out, key=lambda z: (-z.degraded_share, z.cell))


def cross_check(ours: list[Zone], theirs: list[Zone]) -> None:
    """Mark each of our zones by whether GPSJam shows elevated interference (>= MEDIUM_SHARE) in the same cell. Only when GPSJam was read."""
    if not theirs:
        return
    import math

    hot = {(math.floor(z.lat / flags.CELL_DEG), math.floor(z.lon / flags.CELL_DEG)) for z in theirs if z.degraded_share >= flags.MEDIUM_SHARE}
    for z in ours:
        la, lo = z.cell.split(",")
        z.cross_check = "agrees" if (math.floor(float(la) / flags.CELL_DEG), math.floor(float(lo) / flags.CELL_DEG)) in hot else "not_in_gpsjam"
