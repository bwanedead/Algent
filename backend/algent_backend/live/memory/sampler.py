"""
Samplers — turning what the live feeds hold right now into hour values (the only place memory touches a feed's data).

  * ``Sampler`` (stream service): every ``SAMPLE_SECONDS`` it reads the already-built vessel and aircraft snapshot documents
    (never the boards), counts objects per 1-degree cell, per named area and for the world, by class, and notes where
    AIS was heard recently. At the end of each UTC hour it writes the hour's MEAN (``hours.write_hour``).
  * ``record_fires`` / ``record_events`` (timer runs): the FIRMS heat document and the outage / quake events folded the same way.

Counting only: no id, name or track survives. Pure functions below are what the tests drive.
"""

from __future__ import annotations

import time
from collections import defaultdict
from typing import Any, Callable, Iterable

from ..classify import VESSEL_CLASSES
from ..contracts import LiveEvent
from . import flags, hours
from .areas import AREA_CELLS, WORLD, areas_at, cell_of

_V_LON, _V_LAT, _V_CLS, _V_TS = 1, 2, 5, 6          # vessel / aircraft row positions (aircraft share lon, lat, class)


def _bump(out: Any, series: str, place: int | str, by: float = 1.0) -> None:
    out[series][place] += by


def sample_ships(vessels: dict[str, Any], covered: Iterable[int] | None, now: float) -> hours.Values:
    """Counts per class (+ ``ship.all`` for areas and the world) and receiver coverage (``ship.heard``) from a vessels document."""
    out: Any = defaultdict(lambda: defaultdict(float))
    heard: set[int] = set()
    for r in vessels.get("rows", []):
        lat, lon, klass = r[_V_LAT], r[_V_LON], VESSEL_CLASSES[int(r[_V_CLS])]
        cell = cell_of(lat, lon)
        series = f"ship.{klass}"
        _bump(out, series, cell)
        _bump(out, series, WORLD)
        _bump(out, "ship.all", WORLD)
        for a in areas_at(lat, lon):
            _bump(out, series, a.id)
            _bump(out, "ship.all", a.id)
        if now - r[_V_TS] <= flags.RECENT_S:
            heard.add(cell)
    cov = set(covered) if covered is not None else None
    for cell in heard:
        _bump(out, "ship.heard", cell)
    for aid, cells in AREA_CELLS.items():
        base = [c for c in cells if cov is None or c in cov or c in heard]
        if base:
            share = sum(c in heard for c in base) / len(base)
            if share > 0:
                _bump(out, "ship.heard", aid, share)
    return {s: dict(p) for s, p in out.items()}


def sample_air(aircraft: dict[str, Any]) -> hours.Values:
    """Counts per class (+ ``air.all`` for areas and the world); ``support`` (tankers, surveillance) is inside ``military``."""
    out: Any = defaultdict(lambda: defaultdict(float))
    for r in aircraft.get("rows", []):
        lat, lon, cls = r[_V_LAT], r[_V_LON], int(r[_V_CLS])
        klasses = ["civil"] if cls == 0 else ["military", *(["support"] if cls in (2, 3) else [])]
        cell = cell_of(lat, lon)
        areas = areas_at(lat, lon)
        for k in klasses:
            series = f"air.{k}"
            _bump(out, series, cell)
            _bump(out, series, WORLD)
            for a in areas:
                _bump(out, series, a.id)
        _bump(out, "air.all", WORLD)
        for a in areas:
            _bump(out, "air.all", a.id)
    return {s: dict(p) for s, p in out.items()}


class Sampler:
    """Accumulates samples inside the current UTC hour and writes the hour's mean when the hour turns."""

    def __init__(self, source: str = "stream", writer: Callable[..., Any] = hours.write_hour) -> None:
        self.source, self.writer = source, writer
        self.hour: int | None = None
        self.n = 0
        self.last = 0.0
        self.acc: Any = defaultdict(lambda: defaultdict(float))

    def observe(self, vessels: dict[str, Any], aircraft: dict[str, Any], covered: Iterable[int] | None, now: float | None = None) -> bool:
        """Take a sample if one is due. Returns True when one was taken. Never raises (memory must not cost the stream a cycle)."""
        now = time.time() if now is None else now
        hour = hours.hour_of(now)
        try:
            if self.hour is not None and hour != self.hour:
                self.flush()
            if self.hour is not None and self.n and now - self.last < flags.SAMPLE_SECONDS:
                return False
            self.hour = hour
            sample = {**sample_ships(vessels, covered, now), **sample_air(aircraft)}
            for series, places in sample.items():
                for p, v in places.items():
                    self.acc[series][p] += v
            self.n += 1
            self.last = now
            return True
        except Exception:  # noqa: BLE001
            return False

    def flush(self) -> None:
        """Write the hour so far (its mean over the samples taken) and start a fresh one."""
        if self.hour is not None and self.n:
            values = {s: {p: v / self.n for p, v in places.items()} for s, places in self.acc.items()}
            self.writer(self.hour, self.source, self.n, values)
        self.hour, self.n, self.acc = None, 0, defaultdict(lambda: defaultdict(float))


# ── timer-run sources ───────────────────────────────────────────────────────────────────────────
def fire_values(doc: dict[str, Any]) -> hours.Values:
    """The FIRMS heat document (``cells`` = [lon, lat, detections, strongest MW] per 0.25 degree cell, a rolling 24 h picture)
    folded into 1-degree cells, areas and the world: ``fire.count`` (detections) and ``fire.frp`` (the cells' strongest readings summed:
    the document keeps one peak per cell, not every reading, so this is an intensity index, not total radiative power)."""
    out: Any = defaultdict(lambda: defaultdict(float))
    for lon, lat, n, frp in doc.get("cells", []):
        places: list[int | str] = [cell_of(lat, lon), WORLD, *(a.id for a in areas_at(lat, lon))]
        for p in places:
            out["fire.count"][p] += n
            out["fire.frp"][p] += frp
    return {s: dict(p) for s, p in out.items()}


def event_values(feed: str, events: list[LiveEvent]) -> hours.Values:
    """Counts of what is going on now: ongoing outages (``outage.count``) or quakes in the past day (``quake.count``)."""
    series = {"ioda": "outage.count", "usgs": "quake.count"}.get(feed)
    if series is None:
        return {}
    out: Any = defaultdict(float)
    for e in events:
        if feed == "ioda" and e.end is not None:
            continue
        out[WORLD] += 1
        if e.lat is not None and e.lon is not None:
            for a in areas_at(e.lat, e.lon):
                out[a.id] += 1
    return {series: dict(out)}


def record_fires(doc: dict[str, Any], now: float | None = None) -> bool:
    """Write the hour file for a FIRMS run. Never raises."""
    try:
        now = time.time() if now is None else now
        hours.write_hour(hours.hour_of(now), "firms", 1, fire_values(doc))
        return True
    except Exception:  # noqa: BLE001
        return False


def record_events(feed: str, events: list[LiveEvent], now: float | None = None) -> bool:
    """Write the hour file for an outage / quake feed run (the latest run of the hour wins). Never raises."""
    try:
        values = event_values(feed, events)
        if not values:
            return False
        hours.write_hour(hours.hour_of(time.time() if now is None else now), feed, 1, values)
        return True
    except Exception:  # noqa: BLE001
        return False
