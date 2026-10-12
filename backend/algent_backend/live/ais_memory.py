"""
What the ship board remembers beyond the live positions — two small, bounded, disk-backed memories.

``StaticMemory``  MMSI -> [ship type, name, destination, last heard]. Static data is broadcast only every ~6 minutes per ship (and
                  Class B ships send type and name in separate parts), so a fresh process knows nobody's type and every ship reads
                  "other". This is loaded at start and saved every few minutes; entries expire after ``STATIC_KEEP_S`` and the
                  newest ``STATIC_MAX`` are kept.
``Coverage``      the receiver-coverage grid: 1-degree cells in which any AIS position was heard in the last 24 hours. Empty ocean
                  on the map means "no receiver", not "no ships"; this is the layer that says so. Cell id = row * 360 + column
                  with row = floor(lat) + 90 and column = floor(lon) + 180.
"""

from __future__ import annotations

import json
import math
import os
from pathlib import Path
from typing import Any

from . import flags


class StaticMemory:
    def __init__(self) -> None:
        self.m: dict[int, list[Any]] = {}

    def get(self, mmsi: int) -> list[Any] | None:
        return self.m.get(mmsi)

    def put(self, mmsi: int, ship_type: Any, name: Any, dest: Any, now: float) -> None:
        """Merge what a message carried into the record. An absent field never erases a known one; type 0 is "not available"."""
        cur = self.m.get(mmsi, [0, "", "", 0.0])
        t = ship_type if isinstance(ship_type, int) and ship_type > 0 else cur[0]
        self.m[mmsi] = [t, (name or cur[1] or "").strip()[:24], (dest or cur[2] or "").strip()[:24], now]

    def prune(self, now: float) -> None:
        horizon = now - flags.STATIC_KEEP_S
        if len(self.m) > flags.STATIC_MAX or any(v[3] < horizon for v in self.m.values()):
            fresh = [(k, v) for k, v in self.m.items() if v[3] >= horizon]
            fresh.sort(key=lambda kv: -kv[1][3])
            self.m = dict(fresh[:flags.STATIC_MAX])

    @staticmethod
    def write(path: Path, m: dict[int, list[Any]]) -> None:
        _write(path, {str(k): v for k, v in m.items()})

    @classmethod
    def load(cls, path: Path) -> "StaticMemory":
        out = cls()
        for k, v in _read(path).items():
            try:
                out.m[int(k)] = [int(v[0]), str(v[1]), str(v[2]), float(v[3])]
            except (ValueError, TypeError, IndexError):
                continue
        return out


class Coverage:
    def __init__(self) -> None:
        self.seen: dict[int, float] = {}

    @staticmethod
    def cell(lat: float, lon: float) -> int:
        d = flags.COVERAGE_DEG
        return int(math.floor((lat + 90) / d)) * (360 // d) + int(math.floor((lon + 180) / d))

    def hear(self, lat: float, lon: float, ts: float) -> None:
        c = self.cell(lat, lon)
        if self.seen.get(c, 0.0) < ts:
            self.seen[c] = ts

    def prune(self, now: float) -> None:
        self.seen = {c: t for c, t in self.seen.items() if now - t <= flags.COVERAGE_KEEP_S}

    def document(self, as_of: str, now: float) -> dict[str, Any]:
        """The published ``coverage`` document: ``cells`` is the sorted list of covered cell ids."""
        self.prune(now)
        return {"v": 1, "as_of": as_of, "deg": flags.COVERAGE_DEG, "hours": flags.COVERAGE_KEEP_S // 3600, "cells": sorted(self.seen)}

    @staticmethod
    def write(path: Path, seen: dict[int, float]) -> None:
        _write(path, {str(c): int(t) for c, t in seen.items()})

    @classmethod
    def load(cls, path: Path) -> "Coverage":
        out = cls()
        for k, v in _read(path).items():
            try:
                out.seen[int(k)] = float(v)
            except (ValueError, TypeError):
                continue
        return out


def _read(path: Path) -> dict[str, Any]:
    try:
        doc = json.loads(path.read_text(encoding="utf-8"))
        return doc if isinstance(doc, dict) else {}
    except (OSError, ValueError):
        return {}


def _write(path: Path, doc: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(doc, separators=(",", ":"), ensure_ascii=False), encoding="utf-8")
    os.replace(tmp, path)
