"""
Live position boards — the bounded in-memory state behind the map's moving ships and aircraft.

``TrackStore`` keeps a short trail per object (a point at most every ``step`` seconds, at most ``max_pts`` points, nothing
older than ``keep_s``) in compact ``array('i')`` rows, and drops an object's trail the moment the object leaves the board.
``VesselBoard`` holds the latest position per MMSI (expiring after ``AIS_VESSEL_TTL_S``, never more than ``AIS_MAX_VESSELS``,
the freshest kept) and turns it into the published ``vessels`` snapshot. No history beyond that bounded live state is kept.

Snapshot row: ``[mmsi, lon, lat, heading, speed_kn, class, last_seen_unix, name, destination, flag, notable]``
(heading and speed -1 when the ship does not broadcast them; trailing empty fields are left off). ``class`` indexes
``classify.VESSEL_CLASSES``. ``notable`` is a bit set: 1 military or law-enforcement, 2 dark (was moving when last heard, then silent for
``DARK_AFTER_S`` while still on the board), 4 a tanker stopped inside a chokepoint lane.
"""

from __future__ import annotations

from array import array
from typing import Any

from . import flags
from .classify import VESSEL_CLASSES, flag_of, vessel_class
from .contracts import iso
from .regions import GATES, inside

from datetime import datetime, timezone

_NA_SOG = 102.3        # AIS "speed not available"
_NA_HDG = 511          # AIS "true heading not available"
MOVING_KN = 0.5        # below this a vessel counts as stopped (moored, anchored or drifting)
_E4 = 10000


class TrackStore:
    def __init__(self, step_s: int = flags.TRACK_STEP_S, keep_s: int = flags.TRACK_KEEP_S, max_pts: int = flags.TRACK_POINTS) -> None:
        self.step, self.keep, self.max_pts = step_s, keep_s, max_pts
        self.t: dict[int, array] = {}

    def add(self, key: int, ts: float, lat: float, lon: float) -> None:
        a = self.t.get(key)
        if a is None:
            self.t[key] = array("i", (int(ts), round(lat * _E4), round(lon * _E4)))
            return
        if ts - a[-3] < self.step:
            return
        a.extend((int(ts), round(lat * _E4), round(lon * _E4)))
        if len(a) > self.max_pts * 3:
            del a[:3]

    def prune(self, alive: Any, now: float) -> None:
        for key in [k for k in self.t if k not in alive]:
            del self.t[key]
        horizon = now - self.keep
        for key, a in list(self.t.items()):
            while len(a) > 3 and a[0] < horizon:
                del a[:3]

    def shard(self, k: int, n: int) -> dict[str, list[float]]:
        """``{id: [lon, lat, lon, lat, ...]}`` oldest first, for the objects whose id falls in shard ``k`` of ``n`` (two points or more)."""
        out = {}
        for key, a in self.t.items():
            if key % n == k and len(a) >= 6:
                out[str(key)] = [round(a[i] / _E4, 3) for j in range(0, len(a), 3) for i in (j + 2, j + 1)]
        return out


class VesselBoard:
    def __init__(self, ttl: int = flags.AIS_VESSEL_TTL_S, cap: int = flags.AIS_MAX_VESSELS) -> None:
        self.ttl, self.cap = ttl, cap
        self.v: dict[int, list[float]] = {}                  # mmsi -> [lat, lon, heading, speed, seen]
        self.static: dict[int, list[Any]] = {}               # mmsi -> [ship type, name, destination, seen]
        self.name: dict[int, str] = {}                       # names from position metadata (only for vessels on the board)
        self.tracks = TrackStore()

    # ── input ──────────────────────────────────────────────────────────────────────────────
    def message(self, msg: dict[str, Any], now: float) -> None:
        body, meta = msg.get("Message") or {}, msg.get("MetaData") or {}
        mmsi = meta.get("MMSI") or next((b.get("UserID") for b in body.values() if isinstance(b, dict) and b.get("UserID")), None)
        if not mmsi:
            return
        mmsi = int(mmsi)
        st = body.get("ShipStaticData")
        if st:
            self._static(mmsi, st.get("Type"), st.get("Name"), st.get("Destination"), now)
            return
        rep = body.get("StaticDataReport")
        if rep:
            self._static(mmsi, (rep.get("ReportB") or {}).get("ShipType"), (rep.get("ReportA") or {}).get("Name"), None, now)
            return
        pos = body.get("PositionReport") or body.get("StandardClassBPositionReport") or body.get("ExtendedClassBPositionReport")
        lat = meta.get("latitude", (pos or {}).get("Latitude"))
        lon = meta.get("longitude", (pos or {}).get("Longitude"))
        if pos is None or lat is None or lon is None or abs(lat) > 90 or abs(lon) > 180:
            return
        sog = pos.get("Sog")
        hdg = pos.get("TrueHeading")
        if hdg is None or hdg == _NA_HDG or not 0 <= hdg < 360:
            cog = pos.get("Cog")
            hdg = cog if cog is not None and 0 <= cog < 360 and (sog or 0) >= MOVING_KN else -1
        sog = -1.0 if sog is None or sog >= _NA_SOG else float(sog)
        self.v[mmsi] = [float(lat), float(lon), float(hdg), sog, now]
        nm = (meta.get("ShipName") or "").strip()
        if nm:
            self.name[mmsi] = nm[:24]
        self.tracks.add(mmsi, now, lat, lon)

    def _static(self, mmsi: int, ship_type: Any, name: Any, dest: Any, now: float) -> None:
        cur = self.static.get(mmsi, [None, "", "", 0.0])
        self.static[mmsi] = [ship_type if ship_type is not None else cur[0], (name or cur[1] or "").strip()[:24],
                             (dest or cur[2] or "").strip()[:24], now]

    # ── upkeep ─────────────────────────────────────────────────────────────────────────────
    def prune(self, now: float) -> None:
        self.v = {k: r for k, r in self.v.items() if now - r[4] <= self.ttl}
        if len(self.v) > self.cap:                            # keep the freshest `cap`
            keep = sorted(self.v.items(), key=lambda kv: -kv[1][4])[:self.cap]
            self.v = dict(keep)
        self.static = {k: s for k, s in self.static.items() if k in self.v or now - s[3] <= self.ttl}
        if len(self.static) > 2 * self.cap:
            self.static = dict(sorted(self.static.items(), key=lambda kv: -kv[1][3])[:self.cap])
        self.name = {k: n for k, n in self.name.items() if k in self.v}
        self.tracks.prune(self.v, now)

    # ── output ─────────────────────────────────────────────────────────────────────────────
    def snapshot(self, now: float) -> tuple[dict[str, Any], dict[str, dict[str, int]]]:
        """(the published ``vessels`` document, per-gate live counts for the tiles and headlines). Prunes first."""
        self.prune(now)
        rows: list[list[Any]] = []
        counts: dict[str, int] = {c: 0 for c in VESSEL_CLASSES}
        gates = {g.slug: {"in_strait": 0, "moving": 0, "tankers": 0} for g in GATES}
        for mmsi, (lat, lon, hdg, sog, seen) in self.v.items():
            stc = self.static.get(mmsi)
            cls = vessel_class(stc[0] if stc else None)
            counts[VESSEL_CLASSES[cls]] += 1
            nf = 1 if cls == 4 else 0
            if sog >= MOVING_KN and now - seen >= flags.DARK_AFTER_S:
                nf |= 2
            for g in GATES:
                if inside(g.box, lat, lon):
                    c = gates[g.slug]
                    c["in_strait"] += 1
                    c["moving"] += sog >= MOVING_KN
                    c["tankers"] += cls == 0
                    if cls == 0 and 0 <= sog < MOVING_KN:
                        nf |= 4
            row = [mmsi, round(lon, 3), round(lat, 3), round(hdg), round(sog, 1), cls, int(seen),
                   self.name.get(mmsi) or (stc[1] if stc else ""), stc[2] if stc else "", flag_of(mmsi), nf]
            while len(row) > 7 and not row[-1]:
                row.pop()
            rows.append(row)
        as_of = iso(datetime.fromtimestamp(now, tz=timezone.utc))
        doc = {"v": 1, "as_of": as_of, "ttl": self.ttl, "n": len(rows), "classes": list(VESSEL_CLASSES), "counts": counts,
               "f": ["id", "lon", "lat", "hdg", "sog", "cls", "ts", "name", "dest", "flag", "nf"], "rows": rows}
        return doc, gates
