"""
Baselines — what each place and class normally holds at this hour of the week, learned incrementally and kept compact.

One ``Baseline`` per layer (ships, aircraft, fires). For every (series, place) it keeps a small ring per slot: the last
``depth`` values of that slot (ships and aircraft: the same hour of the week over the trailing weeks; fires: the last
observations, one slot), as 16-bit counts (``scale`` units per object). The estimate is computed from the ring when asked
(``robust.normal_of``): median plus MAD, over the slot and its two neighbouring hours when the slot is learned.

  * Learned slot (>= ``min_full`` values): the normal of its own ring (and its +-1 h neighbours, which steadies the spread).
  * Too little history (a young layer, or a place new to it): fall back to the trailing days - the same hour of day on
    every weekday - and mark the normal ``learning``. With fewer than ``min_pool`` pooled values the place is not scored.
  * A place the layer has never held anything at, once the layer is old enough to know, has the ZERO normal: a military
    aircraft over an empty cell is a departure from "none".

Memory is bounded: rings are fixed size, a place with nothing for ``FORGET_DAYS`` is dropped on save. Persisted as one gzip
file per layer (a JSON header, then the raw 16-bit rings). Forward-only: nothing here is back-filled.
"""

from __future__ import annotations

import gzip
import json
import os
import struct
import sys
import zlib
from array import array
from dataclasses import dataclass
from pathlib import Path

from . import flags
from .robust import Normal, normal_of, zero_normal

MISSING = 0xFFFF
HOURS_PER_WEEK = 168


@dataclass(frozen=True)
class Geometry:
    slots: int
    depth: int
    scale: int              # stored units per object (resolution 1/scale)
    min_full: int
    min_pool: int


GEOMETRY: dict[str, Geometry] = {
    "ship": Geometry(HOURS_PER_WEEK, flags.BASELINE_WEEKS, 8, flags.MIN_WEEKS, flags.MIN_POOL),
    "air": Geometry(HOURS_PER_WEEK, flags.BASELINE_WEEKS, 8, flags.MIN_WEEKS, flags.MIN_POOL),
    "fire": Geometry(1, flags.FIRE_DEPTH, 1, flags.FIRE_MIN_OBS, flags.FIRE_MIN_POOL),
}


def slot_of(layer: str, hour: int) -> int:
    """Slot of an epoch hour: Monday 00 UTC = 0 ... Sunday 23 = 167 (fires have one slot)."""
    return 0 if GEOMETRY[layer].slots == 1 else (((hour // 24) + 3) % 7) * 24 + hour % 24      # 1970-01-01 was a Thursday


def key_of(series: str, place: int | str) -> str:
    return f"{series}|{place}"


def split_key(key: str) -> tuple[str, int | str]:
    series, p = key.split("|", 1)
    return series, int(p) if p.isdigit() else p


class Baseline:
    def __init__(self, layer: str) -> None:
        self.layer, self.geo = layer, GEOMETRY[layer]
        self.index: dict[str, int] = {}
        self.vals = array("H")
        self.active = array("H")            # last epoch DAY on which the place held anything (for forgetting)
        self.first_hour: int | None = None
        self.observed = 0                    # hours (fires: observations) fed so far

    # ── layout ────────────────────────────────────────────────────────────────────────────
    def _base(self, row: int, slot: int) -> int:
        return (row * self.geo.slots + slot) * self.geo.depth

    def mature(self) -> bool:
        """The layer has been watched long enough that an absent place was genuinely empty (not just unseen)."""
        return self.observed >= self.geo.min_full * self.geo.slots

    def _add_row(self, key: str, day: int) -> int:
        row = len(self.index)
        self.index[key] = row
        self.vals.extend(array("H", [0 if self.mature() else MISSING]) * (self.geo.slots * self.geo.depth))
        self.active.append(day)
        return row

    def window(self, row: int, slot: int) -> list[float]:
        b = self._base(row, slot)
        return [v / self.geo.scale for v in self.vals[b:b + self.geo.depth] if v != MISSING]

    # ── reading ───────────────────────────────────────────────────────────────────────────
    def estimate(self, key: str, slot: int) -> Normal | None:
        row = self.index.get(key)
        if row is None:
            return zero_normal() if self.mature() else None
        g = self.geo
        own = self.window(row, slot)
        if len(own) >= g.min_full:
            if g.slots == 1:
                return normal_of(own)
            return normal_of(own + self.window(row, (slot - 1) % g.slots) + self.window(row, (slot + 1) % g.slots))
        if g.slots == 1:
            pool = own
        else:                                # trailing days: the same hour of day (+-1 h) on every weekday
            hod = slot % 24
            pool = [v for d in range(7) for dh in (-1, 0, 1) for v in self.window(row, (d * 24 + hod + dh) % g.slots)]
        return normal_of(pool, learning=True) if len(pool) >= g.min_pool else None

    def keys(self) -> list[str]:
        return list(self.index)

    # ── writing ───────────────────────────────────────────────────────────────────────────
    def put(self, key: str, slot: int, value: float, day: int) -> None:
        """Shift ``value`` into the slot's ring (oldest out). Creates the place on first sight."""
        row = self.index.get(key)
        if row is None:
            row = self._add_row(key, day)
        b, d = self._base(row, slot), self.geo.depth
        self.vals[b:b + d - 1] = self.vals[b + 1:b + d]
        self.vals[b + d - 1] = min(MISSING - 1, max(0, round(value * self.geo.scale)))
        if value > 0:
            self.active[row] = day

    def note_hour(self, hour: int) -> None:
        self.first_hour = hour if self.first_hour is None else self.first_hour
        self.observed += 1

    def forget(self, today_day: int) -> int:
        """Drop places with nothing for ``FORGET_DAYS``; returns how many."""
        keep = [(k, r) for k, r in self.index.items() if today_day - self.active[r] <= flags.FORGET_DAYS]
        if len(keep) == len(self.index):
            return 0
        width = self.geo.slots * self.geo.depth
        vals, active = array("H"), array("H")
        for _k, r in keep:
            vals.extend(self.vals[r * width:(r + 1) * width])
            active.append(self.active[r])
        dropped = len(self.index) - len(keep)
        self.index, self.vals, self.active = {k: i for i, (k, _r) in enumerate(keep)}, vals, active
        return dropped

    # ── disk ──────────────────────────────────────────────────────────────────────────────
    def save(self, path: Path) -> None:
        head = json.dumps({"v": 1, "layer": self.layer, "slots": self.geo.slots, "depth": self.geo.depth, "first": self.first_hour,
                           "observed": self.observed, "keys": list(self.index), "active": list(self.active)},
                          separators=(",", ":")).encode()
        body = array("H", self.vals)
        if sys.byteorder == "big":
            body.byteswap()
        path.parent.mkdir(parents=True, exist_ok=True)
        tmp = path.with_suffix(path.suffix + ".tmp")
        tmp.write_bytes(gzip.compress(struct.pack(">I", len(head)) + head + body.tobytes(), compresslevel=6, mtime=0))
        os.replace(tmp, path)

    @classmethod
    def load(cls, layer: str, path: Path) -> "Baseline":
        out = cls(layer)
        try:
            raw = gzip.decompress(path.read_bytes())
            (n,) = struct.unpack(">I", raw[:4])
            head = json.loads(raw[4:4 + n])
            if (head["slots"], head["depth"]) != (out.geo.slots, out.geo.depth):
                return out                    # the geometry was retuned: the old rings no longer fit, learn afresh
            vals = array("H")
            vals.frombytes(raw[4 + n:])
            if sys.byteorder == "big":
                vals.byteswap()
            if len(vals) != len(head["keys"]) * out.geo.slots * out.geo.depth:
                return out
            out.index = {k: i for i, k in enumerate(head["keys"])}
            out.vals, out.active = vals, array("H", head["active"])
            out.first_hour, out.observed = head["first"], head["observed"]
        except (OSError, ValueError, KeyError, struct.error, EOFError, zlib.error):
            return cls(layer)
        return out
