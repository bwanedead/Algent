"""
The sky board — live aircraft for the map: every military-flagged aircraft (adsb.lol ``/v2/mil``, one call) plus civil traffic
sampled by sweeping area queries over the world's busiest airspace (adsb.lol has no worldwide dump; ``/v2/point`` takes
a 250 nautical mile radius). Each cycle polls the next ``CIVIL_POLLS_PER_CYCLE`` hubs of ``regions.CIVIL_HUBS``, so the
planet is swept every few minutes at a polite rate. State is bounded: civil aircraft expire after ``CIVIL_TTL_S``,
military after ``MIL_TTL_S``, never more than ``AIRCRAFT_MAX``.

Published row: ``[id, lon, lat, heading, speed_kn, class, last_seen_unix, callsign, type, altitude_ft]`` where ``class`` is
0 civil, 1 other military, 2 tanker, 3 surveillance, 4 airlift, 5 fighter/bomber (``regions.aircraft_class``). ``id`` is a
hash of the ICAO address: neither the address nor the registration is published; the callsign is what the aircraft broadcasts.
HONEST LIMIT: only aircraft that broadcast ADS-B and are heard by volunteer receivers appear; many military flights fly silent,
and the civil picture is a sample of the busiest airspace, not every aircraft.
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Any, Callable

from . import flags
from .board import TrackStore
from .classify import aircraft_id
from .contracts import iso
from .regions import CIVIL_HUBS, aircraft_class

MIL_URL = "https://api.adsb.lol/v2/mil"
POINT_URL = "https://api.adsb.lol/v2/point/{lat}/{lon}/250"


class SkyBoard:
    def __init__(self) -> None:
        self.a: dict[int, list[Any]] = {}      # id -> [lat, lon, hdg, spd, seen, cls, callsign, type, alt]
        self.tracks = TrackStore(step_s=120)
        self.cycle = 0

    def ingest(self, text: str, now: float, *, all_military: bool) -> int:
        n = 0
        for ac in json.loads(text).get("ac") or []:
            lat, lon = ac.get("lat"), ac.get("lon")
            if not isinstance(lat, (int, float)) or not isinstance(lon, (int, float)) or not ac.get("hex"):
                continue
            mil = all_military or bool(int(ac.get("dbFlags") or 0) & 1)
            hdg = ac.get("track", ac.get("true_heading"))
            alt = ac.get("alt_baro")
            aid = aircraft_id(ac["hex"])
            rec = [float(lat), float(lon), float(hdg) if isinstance(hdg, (int, float)) else -1.0,
                   float(ac["gs"]) if isinstance(ac.get("gs"), (int, float)) else -1.0, now,
                   aircraft_class(ac.get("t", ""), mil), (ac.get("flight") or "").strip()[:10], (ac.get("t") or "")[:5],
                   int(alt) if isinstance(alt, (int, float)) else (0 if alt == "ground" else -1)]
            prev = self.a.get(aid)
            if prev and prev[4] > now:      # never replace with something older
                continue
            self.a[aid] = rec
            self.tracks.add(aid, now, lat, lon)
            n += 1
        return n

    def poll(self, get: Callable[..., str], now: float) -> dict[str, Any]:
        """One cycle: all military, plus the next civil hubs. A failing call is skipped, never fatal."""
        got = {"mil": 0, "civil": 0, "errors": 0}
        try:
            got["mil"] = self.ingest(get(MIL_URL), now, all_military=True)
        except Exception:  # noqa: BLE001
            got["errors"] += 1
        for _ in range(flags.CIVIL_POLLS_PER_CYCLE):
            lat, lon = CIVIL_HUBS[self.cycle % len(CIVIL_HUBS)]
            self.cycle += 1
            try:
                got["civil"] += self.ingest(get(POINT_URL.format(lat=lat, lon=lon)), now, all_military=False)
            except Exception:  # noqa: BLE001
                got["errors"] += 1
        return got

    def prune(self, now: float) -> None:
        self.a = {k: r for k, r in self.a.items() if now - r[4] <= (flags.CIVIL_TTL_S if r[5] == 0 else flags.MIL_TTL_S)}
        if len(self.a) > flags.AIRCRAFT_MAX:              # keep every military aircraft, then the freshest civil
            mil = {k: r for k, r in self.a.items() if r[5] != 0}
            civ = sorted(((k, r) for k, r in self.a.items() if r[5] == 0), key=lambda kv: -kv[1][4])[:max(0, flags.AIRCRAFT_MAX - len(mil))]
            self.a = {**mil, **dict(civ)}
        self.tracks.prune(self.a, now)

    def snapshot(self, now: float) -> dict[str, Any]:
        self.prune(now)
        rows, counts = [], {"civil": 0, "military": 0}
        for aid, (lat, lon, hdg, spd, seen, cls, call, typ, alt) in self.a.items():
            counts["civil" if cls == 0 else "military"] += 1
            row = [aid, round(lon, 3), round(lat, 3), round(hdg), round(spd), cls, int(seen), call, typ, alt]
            while len(row) > 7 and row[-1] in ("", -1):
                row.pop()
            rows.append(row)
        return {"v": 1, "as_of": iso(datetime.fromtimestamp(now, tz=timezone.utc)), "n": len(rows), "counts": counts,
                "classes": ["civil", "military", "tanker", "surveillance", "airlift", "fighter"],
                "f": ["id", "lon", "lat", "hdg", "spd", "cls", "ts", "callsign", "type", "alt"], "rows": rows}
