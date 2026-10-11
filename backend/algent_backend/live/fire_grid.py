"""
Fire grid — the world's satellite heat detections folded into 0.25 degree cells (pure; no I/O).

Why a grid: a day of VIIRS holds hundreds of thousands of detections. The map's heat layer only needs, per ~27 km cell,
how many readings there were and how strong the strongest was; that is a payload of tens of thousands of small rows
rather than a million. NOTABLE cells (the day's extremes by intensity or by concentration, not a fixed number) become
individual events. Memory is bounded by the number of occupied cells, never by the number of detections.
"""

from __future__ import annotations

import math
from typing import Any, NamedTuple

from . import flags


class Cell(NamedTuple):
    lat: float          # cell centre
    lon: float
    n: int              # detections
    frp: float          # strongest fire radiative power, MW
    last: int           # latest acquisition as YYYYMMDDHHMM


class FireGrid:
    def __init__(self, cell_deg: float = flags.FIRE_GRID_DEG) -> None:
        self.cell = cell_deg
        self.cells: dict[tuple[int, int], list[float]] = {}     # key -> [n, max frp, last]
        self.total = 0

    def add(self, lat: float, lon: float, frp: float, stamp: int = 0) -> None:
        key = (math.floor(lat / self.cell), math.floor(lon / self.cell))
        c = self.cells.get(key)
        if c is None:
            self.cells[key] = [1, frp, stamp]
        else:
            c[0] += 1
            c[1] = max(c[1], frp)
            c[2] = max(c[2], stamp)
        self.total += 1

    def rows(self) -> list[Cell]:
        """Occupied cells, strongest first."""
        out = [Cell(round((k[0] + 0.5) * self.cell, 3), round((k[1] + 0.5) * self.cell, 3), int(v[0]), v[1], int(v[2]))
               for k, v in self.cells.items()]
        out.sort(key=lambda c: (-c.frp, -c.n))
        return out

    def doc(self, as_of: str) -> dict[str, Any]:
        """The published heat document: ``cells`` are ``[lon, lat, detections, strongest MW]``, strongest first, capped."""
        cells = self.rows()[:flags.FIRE_MAX_CELLS]
        return {"v": 1, "as_of": as_of, "cell_deg": self.cell, "detections": self.total, "occupied": len(self.cells),
                "cells": [[c.lon, c.lat, c.n, round(c.frp)] for c in cells]}


def quantile(values: list[float], q: float) -> float:
    s = sorted(values)
    return s[min(len(s) - 1, max(0, math.ceil(q * len(s)) - 1))] if s else 0.0


def notable(cells: list[Cell], skip: Any = None) -> list[Cell]:
    """The day's extreme cells: strongest reading OR detection count in the top ``1 - NOTABLE_QUANTILE`` of the day's cells.
    ``skip(lat, lon)`` drops cells already covered elsewhere (a watched box). One blaze, one event: cells within
    ``NOTABLE_SEPARATION_DEG`` of a chosen one are passed over."""
    if not cells:
        return []
    q_frp = quantile([c.frp for c in cells], flags.NOTABLE_QUANTILE)
    q_n = quantile([float(c.n) for c in cells], flags.NOTABLE_QUANTILE)
    hot = sorted((c for c in cells if c.frp >= q_frp or c.n >= q_n), key=lambda c: (-c.frp, -c.n))
    chosen: list[Cell] = []
    for c in hot:
        if skip and skip(c.lat, c.lon):
            continue
        if any(abs(c.lat - k.lat) < flags.NOTABLE_SEPARATION_DEG and abs(c.lon - k.lon) < flags.NOTABLE_SEPARATION_DEG for k in chosen):
            continue
        chosen.append(c)
        if len(chosen) >= flags.MAX_NOTABLE_FIRES:
            break
    return chosen
