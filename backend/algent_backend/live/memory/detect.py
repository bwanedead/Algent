"""
Detection — one observed hour at a time: score every place against its baseline, follow the sustained runs, screen out data artefacts.

``Detector.step(hour)`` does, for each layer the hour observed (an unobserved layer is skipped entirely: it neither flags nor
teaches the baseline anything):

  1. score every (series, place) - the cells and named areas that hold, or normally hold, anything - against its baseline:
     robust z = (value - median) / sigma (``robust.py``);
  2. screen: a "below normal" is NOT an event when it could be a data gap (see ``_gap_reason``): the rest of the place's traffic
     fell too, the place's receivers were not heard, the normal was too thin to fall from, or the whole world layer dipped;
  3. follow runs: a place flagged (|z| >= Z_ENTER, learning baselines: LEARNING_Z) opens a run; it goes on while |z| >= Z_EXIT in the
     same direction; a run is CONFIRMED once it has lasted ``PERSIST_HOURS`` observations; it closes when the score falls back, flips
     sign, or the source goes quiet for ``MAX_GAP_HOURS``;
  4. teach the baselines with this hour's values - except the values of a run opened less than ``FREEZE_HOURS`` ago.

It returns events (``open`` when a run is confirmed, ``close`` when a confirmed run ends) and counts of what was screened out.
The decision is explicit state (``Run``), persisted by ``tick.py``; nothing here reads the clock or the disk.
"""

from __future__ import annotations

import math
from collections import defaultdict
from dataclasses import asdict, dataclass
from typing import Any, NamedTuple

from . import flags, robust
from .areas import CLASSES, PARTITION, SCORED, WORLD, layer_of
from .baseline import Baseline, key_of, slot_of, split_key
from .hours import Hour, day_of
from .robust import Normal

#: Fires reported only when ABOVE normal: a night of cloud, or a satellite pass that missed, makes fires "fall" without any change on the ground.
FIRE_BELOW_REPORTED = False

SOURCE_OF = {"ship": "stream", "air": "stream", "fire": "firms"}


@dataclass
class Run:
    series: str
    place: int | str
    direction: int                  # +1 above normal, -1 below
    start: int                      # epoch hour the run opened
    last_flag: int                  # last hour it was still flagged
    obs: int = 1                    # consecutive flagged observations
    peak: float = 0.0               # strongest score (absolute)
    zsum: float = 0.0
    value: float = 0.0              # latest value / latest normal
    normal: float = 0.0
    learning: bool = False
    confirmed: bool = False

    @property
    def key(self) -> str:
        return key_of(self.series, self.place)

    @property
    def mean_score(self) -> float:
        return self.zsum / max(1, self.obs)

    def to_json(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_json(cls, d: dict[str, Any]) -> "Run":
        return cls(**d)


class Event(NamedTuple):
    kind: str                       # open | close
    run: Run
    end: int | None                 # epoch hour the run ended (close only)


def persist_needed(series: str) -> int:
    return flags.FIRE_PERSIST_OBS if layer_of(series) == "fire" else flags.PERSIST_HOURS


def enter_z(normal: Normal) -> float:
    return flags.LEARNING_Z if normal.learning else flags.Z_ENTER


class Detector:
    def __init__(self, baselines: dict[str, Baseline], runs: dict[str, Run]) -> None:
        self.bl, self.runs = baselines, runs
        self.screened: dict[str, int] = defaultdict(int)

    # ── one hour ──────────────────────────────────────────────────────────────────────────
    def step(self, hour: Hour) -> list[Event]:
        events: list[Event] = []
        self.screened = defaultdict(int)
        for layer in SCORED:
            if not hour.observed(SOURCE_OF[layer], 1 if layer == "fire" else flags.MIN_HOUR_SAMPLES):
                events += self._expire(layer, hour.hour)
                continue
            events += self._layer(layer, hour)
        return events

    def _expire(self, layer: str, h: int) -> list[Event]:
        out = []
        for rk, run in list(self.runs.items()):
            if layer_of(run.series) == layer and h - run.last_flag > flags.MAX_GAP_HOURS:
                out += self._close(rk, run.last_flag + 1)
        return out

    def _layer(self, layer: str, hour: Hour) -> list[Event]:
        h, bl = hour.hour, self.bl[layer]
        slot, day = slot_of(layer, h), day_of(h)
        series_list = [f"{layer}.{k}" for k in CLASSES[layer]]
        known: dict[str, set[int | str]] = defaultdict(set)
        for key in bl.keys():
            s, p = split_key(key)
            known[s].add(p)
        places: dict[str, set[int | str]] = {}
        for s in series_list:
            places[s] = known[s] | set(hour.values.get(s, {}))
        normals: dict[tuple[str, int | str], Normal | None] = {
            (s, p): bl.estimate(key_of(s, p), slot) for s in series_list for p in places[s]}
        world = self._world_low(layer, hour, bl, slot)

        events: list[Event] = []
        seen_runs: set[str] = set()
        for (s, p), nm in normals.items():
            if nm is None or p == WORLD:
                continue
            x = hour.values.get(s, {}).get(p, 0.0)
            z = robust.score(x, nm)
            rk = key_of(s, p)
            events += self._follow(rk, s, p, x, z, nm, h, layer, hour, normals, world)
            seen_runs.add(rk)
        for rk, run in list(self.runs.items()):                  # a run whose place was not scored this hour is no longer flagged
            if layer_of(run.series) == layer and rk not in seen_runs:
                events += self._close(rk, run.last_flag + 1)

        self._teach(bl, layer, hour, series_list, places, slot, day)
        bl.note_hour(h)
        return events

    # ── screening ─────────────────────────────────────────────────────────────────────────
    def _world_low(self, layer: str, hour: Hour, bl: Baseline, slot: int) -> bool:
        if layer == "fire":
            return False
        nm = bl.estimate(key_of(f"{layer}.all", WORLD), slot)
        x = hour.values.get(f"{layer}.all", {}).get(WORLD, 0.0)
        return nm is not None and robust.score(x, nm) <= -flags.Z_EXIT

    def _gap_reason(self, s: str, p: int | str, nm: Normal, x: float, hour: Hour,
                    normals: dict[tuple[str, int | str], Normal | None], world: bool) -> str:
        """Why a below-normal reading may be a data artefact ('' when it may stand)."""
        layer = layer_of(s)
        if layer == "fire":
            return "" if FIRE_BELOW_REPORTED else "fire_below"
        if nm.median < flags.MIN_LOW_NORMAL:
            return "thin_normal"
        if world:
            return "world_feed_low"
        part = PARTITION[layer]
        total_x = sum(hour.values.get(f"{layer}.{k}", {}).get(p, 0.0) for k in part)
        total_n = sum((normals.get((f"{layer}.{k}", p)) or robust.zero_normal()).median for k in part)
        own_x = x
        own_n = nm.median
        rest_n = total_n - own_n
        if rest_n < flags.MIN_COMPANION:
            return "no_companion"
        z_rest = ((total_x - own_x) - rest_n) / max(math.sqrt(rest_n), 1.0)
        if z_rest <= -flags.Z_EXIT:
            return "place_quiet"
        if layer == "ship" and hour.values.get("ship.heard", {}).get(p, 0.0) < flags.HEARD_SHARE:
            return "no_receiver"
        return ""

    # ── runs ──────────────────────────────────────────────────────────────────────────────
    def _follow(self, rk: str, s: str, p: int | str, x: float, z: float, nm: Normal, h: int, layer: str, hour: Hour,
                normals: dict[tuple[str, int | str], Normal | None], world: bool) -> list[Event]:
        direction = (z > 0) - (z < 0)
        ok_dir = direction != 0
        if ok_dir and direction < 0:
            reason = self._gap_reason(s, p, nm, x, hour, normals, world)
            if reason:
                if abs(z) >= flags.Z_ENTER and reason != "fire_below" and reason != "thin_normal":
                    self.screened[reason] += 1
                ok_dir = False
        run = self.runs.get(rk)
        out: list[Event] = []
        if run is not None:
            if ok_dir and direction == run.direction and abs(z) >= flags.Z_EXIT:
                run.obs += 1
                run.last_flag = h
                run.peak = max(run.peak, abs(z))
                run.zsum += abs(z)
                run.value, run.normal, run.learning = x, nm.median, run.learning and nm.learning
                if not run.confirmed and run.obs >= persist_needed(s) and (not run.learning or run.peak >= flags.LEARNING_Z):
                    run.confirmed = True
                    out.append(Event("open", run, None))
                return out
            out += self._close(rk, run.last_flag + 1)
        if ok_dir and abs(z) >= enter_z(nm):
            run = Run(s, p, direction, h, h, 1, abs(z), abs(z), x, nm.median, nm.learning)
            self.runs[rk] = run
            if persist_needed(s) <= 1:
                run.confirmed = True
                out.append(Event("open", run, None))
        return out

    def _close(self, rk: str, end: int) -> list[Event]:
        run = self.runs.pop(rk, None)
        return [Event("close", run, end)] if run is not None and run.confirmed else []

    # ── teaching ──────────────────────────────────────────────────────────────────────────
    def _teach(self, bl: Baseline, layer: str, hour: Hour, series_list: list[str], places: dict[str, set[int | str]],
               slot: int, day: int) -> None:
        h = hour.hour
        for s in series_list:
            for p in places[s]:
                run = self.runs.get(key_of(s, p))
                if run is not None and h - run.start < flags.FREEZE_HOURS:
                    continue                                  # an incident must not teach the baseline that it is normal
                bl.put(key_of(s, p), slot, hour.values.get(s, {}).get(p, 0.0), day)
        if layer != "fire":                                    # the world total, for the feed-outage guard
            bl.put(key_of(f"{layer}.all", WORLD), slot, hour.values.get(f"{layer}.all", {}).get(WORLD, 0.0), day)
