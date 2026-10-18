"""
The lane tracker — turns the positions the stream service already hears into counts of ships moving along the lane network.

Every cycle the tracker looks at each trade carrier on the board. A ship inside a place (``network.place_at``) that is not the place it
was last in has made a HOP: ``route`` gives the chain of lanes it must have sailed, and each lane of the chain gets one count for that
day and that ship class ("observed" when the two places are neighbours, "inferred" when the hop spans several lanes). The place the
ship entered also gets a VISIT. Nothing else about the ship is kept: one last place and time per vessel, and per day the lane and
visit counts, the hours the tracker was watching, and a short sample of observed hop durations per lane.

Forward-only and incremental: a restart resumes from the saved last places; a hop is only believed within ``HOP_MAX_DAYS`` and at a
speed a ship can make. Counts are of what terrestrial AIS heard: a ship dark across a whole ocean still counts once it reappears in a
place, on every lane between, but a ship that never reappears is never counted. The numbers are comparable with themselves over time.
"""

from __future__ import annotations

from collections.abc import Callable
from datetime import datetime, timezone
from typing import Any

from . import flags, store
from .classes import IDS, flow_class
from .network import place_at, route

_LAST = "tracker.json.gz"
_DAYS = "days.json"


def day_of(ts: float) -> str:
    return datetime.fromtimestamp(ts, tz=timezone.utc).strftime("%Y-%m-%d")


class LaneTracker:
    def __init__(self, last: dict[int, list[Any]] | None = None, days: dict[str, dict[str, Any]] | None = None,
                 samples: dict[str, list[float]] | None = None) -> None:
        self.last: dict[int, list[Any]] = last or {}        # mmsi -> [place, last seen there, place before, when it entered `place`]
        self.days: dict[str, dict[str, Any]] = days or {}   # day -> {"secs", "lanes": {"a>b": {cls: [observed, inferred]}}, "visits": {place: {cls: n}}}
        self.samples: dict[str, list[float]] = samples or {}   # "a>b" -> recent observed hop durations in hours
        self.last_cycle = 0.0
        self.last_persist = 0.0

    # ── input ──────────────────────────────────────────────────────────────────────────────────
    def _day(self, ts: float) -> dict[str, Any]:
        return self.days.setdefault(day_of(ts), {"secs": 0.0, "lanes": {}, "visits": {}})

    def observe(self, mmsi: int, lat: float, lon: float, ts: float, cls_of: Callable[[], str | None]) -> bool:
        """Fold one position in. ``cls_of`` names the vessel's flow class (called only when the vessel enters a new place). Returns True
        when a hop was counted."""
        place = place_at(lat, lon)
        if place is None:
            return False
        rec = self.last.get(mmsi)
        if rec is not None:
            if ts < rec[1]:
                return False
            if rec[0] == place:
                rec[1] = ts
                return False
        cls = cls_of()
        if cls is None:
            return False
        if rec is None:
            self.last[mmsi] = [place, ts, "", ts]
            self._visit(place, cls, ts)
            return False
        origin, since = rec[0], rec[3]
        if place == rec[2] and ts - since < flags.FLICKER_S:          # straight back to where it came from: one visit, not two hops
            self.last[mmsi] = [place, ts, origin, ts]
            return False
        self.last[mmsi] = [place, ts, origin, ts]
        self._visit(place, cls, ts)
        return self._hop(origin, place, cls, rec[1], ts)

    def _visit(self, place: str, cls: str, ts: float) -> None:
        v = self._day(ts)["visits"].setdefault(place, {})
        v[cls] = v.get(cls, 0) + 1

    def _hop(self, origin: str, place: str, cls: str, left: float, ts: float) -> bool:
        hours = (ts - left) / 3600.0
        if hours <= 0 or hours > flags.HOP_MAX_DAYS * 24:
            return False
        found = route(origin, place)
        if found is None or found[1] / hours > flags.MAX_SPEED_KMH:
            return False
        path, _km = found
        lanes = self._day(ts)["lanes"]
        direct = len(path) == 2
        for a, b in zip(path, path[1:]):
            key = f"{a}>{b}"
            slot = lanes.setdefault(key, {}).setdefault(cls, [0, 0])
            slot[0 if direct else 1] += 1
        if direct:
            s = self.samples.setdefault(f"{path[0]}>{path[1]}", [])
            s.append(round(hours, 1))
            del s[:-flags.HOP_SAMPLES]
        return True

    # ── the stream service's cycle ─────────────────────────────────────────────────────────────
    def cycle(self, board: Any, now: float) -> dict[str, Any] | None:
        """One pass over the vessel board, when one is due. Returns a small account (None when it was not time yet)."""
        if self.last_cycle and now - self.last_cycle < flags.CYCLE_SECONDS:
            return None
        watched = min(now - self.last_cycle, 2 * flags.CYCLE_SECONDS) if self.last_cycle else 0.0
        self.last_cycle = now
        hops = 0
        for mmsi, row in board.v.items():
            hops += self.observe(mmsi, row[0], row[1], row[4], lambda m=mmsi: board_class(board, m))
        self._day(now)["secs"] += watched
        self.prune(now)
        return {"hops": hops, "tracked": len(self.last)}

    # ── bounds and disk ────────────────────────────────────────────────────────────────────────
    def prune(self, now: float) -> None:
        horizon = now - flags.STATE_KEEP_DAYS * 86400
        if len(self.last) > flags.STATE_MAX or any(r[1] < horizon for r in self.last.values()):
            fresh = sorted(((m, r) for m, r in self.last.items() if r[1] >= horizon), key=lambda kv: -kv[1][1])
            self.last = dict(fresh[:flags.STATE_MAX])
        for d in sorted(self.days)[:-flags.DAY_KEEP]:
            del self.days[d]

    def persist_due(self, now: float) -> bool:
        return now - self.last_persist >= flags.PERSIST_SECONDS

    def snapshot(self, now: float) -> dict[str, Any]:
        """Serialisable copies of the state, taken on the loop thread (the write may run on another)."""
        self.last_persist = now
        return {"last": {str(m): list(r) for m, r in self.last.items()},
                "days": {"v": 1, "days": {d: {"secs": round(v["secs"], 1), "lanes": {k: {c: list(x) for c, x in cs.items()} for k, cs in v["lanes"].items()},
                                              "visits": {p: dict(cs) for p, cs in v["visits"].items()}} for d, v in self.days.items()},
                         "samples": {k: list(v) for k, v in self.samples.items()}}}

    @staticmethod
    def write(docs: dict[str, Any]) -> None:
        store.write_json(_LAST, docs["last"], gz=True)
        store.write_json(_DAYS, docs["days"])

    @classmethod
    def load(cls) -> "LaneTracker":
        last: dict[int, list[Any]] = {}
        for k, r in (store.read_json(_LAST, {}) or {}).items():
            try:
                last[int(k)] = [str(r[0]), float(r[1]), str(r[2]), float(r[3])]
            except (ValueError, TypeError, IndexError):
                continue
        doc = store.read_json(_DAYS, {}) or {}
        days = {d: {"secs": float(v.get("secs", 0.0)), "lanes": v.get("lanes", {}), "visits": v.get("visits", {})} for d, v in (doc.get("days") or {}).items()}
        return cls(last, days, {k: [float(x) for x in v] for k, v in (doc.get("samples") or {}).items()})


def board_class(board: Any, mmsi: int) -> str | None:
    """A board vessel's flow class from its remembered AIS type and name."""
    rec = board.static.get(mmsi)
    return flow_class(rec[0] if rec else None, board.name.get(mmsi) or (rec[1] if rec else ""))


__all__ = ["LaneTracker", "board_class", "day_of", "IDS"]
