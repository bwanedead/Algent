"""
The sky board — live aircraft for the map, merged by ICAO address from two kinds of source, freshest position winning:

  * OpenSky Network ``/api/states/all`` (``opensky.py``): the whole world's state vectors in one call — the backbone of civil coverage;
  * adsb.lol: every military-flagged aircraft (``/v2/mil``, one call; its ``dbFlags`` are the only military marker we have) plus area
    queries (``/v2/point``, 250 nautical miles) over the busiest airspace, ``CIVIL_POLLS_PER_CYCLE`` hubs of ``regions.CIVIL_HUBS``
    per cycle, which fill what OpenSky's volunteer receivers miss.

State is bounded: each record expires after its own ttl (adsb.lol civil ``CIVIL_TTL_S``, military ``MIL_TTL_S``, OpenSky a little
over two of its poll intervals), never more than ``AIRCRAFT_MAX`` (military kept, then the freshest civil). The board is touched by the
event loop and by worker threads, so every mutation and the snapshot take one lock.

Published row: ``[id, lon, lat, heading, speed_kn, class, last_seen_unix, callsign, type, altitude_ft]`` where ``class`` is
0 civil, 1 other military, 2 tanker, 3 surveillance, 4 airlift, 5 fighter/bomber (``regions.aircraft_class``). ``id`` is a
hash of the ICAO address: neither the address nor the registration is published; the callsign is what the aircraft broadcasts.
HONEST LIMIT: only aircraft that broadcast ADS-B/Mode S and are heard by volunteer receivers appear (dense in North America, Europe
and parts of Asia; thin over oceans, Africa, Russia and China); many military flights fly silent. OpenSky-only aircraft have no type code.
"""

from __future__ import annotations

import json
import threading
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
        self.a: dict[int, list[Any]] = {}      # id -> [lat, lon, hdg, spd, seen, cls, callsign, type, alt, ttl]
        self.tracks = TrackStore(step_s=flags.AIR_TRACK_STEP_S, max_pts=flags.AIR_TRACK_POINTS)
        self.cycle = 0
        self.lock = threading.RLock()

    def merge(self, aid: int, rec: list[Any]) -> bool:
        """Insert ``rec`` unless the board already holds a fresher position. A known military class and type code are kept when the
        newcomer is a civil/typeless sighting of the same aircraft (OpenSky has neither military flags nor type codes)."""
        with self.lock:
            prev = self.a.get(aid)
            if prev is not None:
                if prev[4] > rec[4]:
                    return False
                if prev[5] != 0 and rec[5] == 0:
                    rec[5], rec[9] = prev[5], max(rec[9], prev[9])
                rec[7] = rec[7] or prev[7]
                rec[6] = rec[6] or prev[6]
            self.a[aid] = rec
            self.tracks.add(aid, rec[4], rec[0], rec[1])
            return True

    def ingest(self, text: str, now: float, *, all_military: bool) -> int:
        """adsb.lol payload (``/v2/mil`` or a ``/v2/point`` area)."""
        n = 0
        for ac in json.loads(text).get("ac") or []:
            lat, lon = ac.get("lat"), ac.get("lon")
            if not isinstance(lat, (int, float)) or not isinstance(lon, (int, float)) or not ac.get("hex"):
                continue
            mil = all_military or bool(int(ac.get("dbFlags") or 0) & 1)
            hdg = ac.get("track", ac.get("true_heading"))
            alt = ac.get("alt_baro")
            cls = aircraft_class(ac.get("t", ""), mil)
            rec = [float(lat), float(lon), float(hdg) if isinstance(hdg, (int, float)) else -1.0,
                   float(ac["gs"]) if isinstance(ac.get("gs"), (int, float)) else -1.0, now,
                   cls, (ac.get("flight") or "").strip()[:10], (ac.get("t") or "")[:5],
                   int(alt) if isinstance(alt, (int, float)) else (0 if alt == "ground" else -1),
                   flags.CIVIL_TTL_S if cls == 0 else flags.MIL_TTL_S]
            n += self.merge(aircraft_id(ac["hex"]), rec)
        return n

    def ingest_opensky(self, states: list[list[Any]], now: float, ttl: float) -> int:
        """OpenSky ``states`` rows (see opensky.py for the columns): position time is the sighting time, so a stale vector never
        displaces a fresher adsb.lol one."""
        from .ingest.opensky import parse_state

        n = 0
        for row in states:
            got = parse_state(row, now)
            if got is None:
                continue
            icao, rec = got
            rec.append(ttl)
            n += self.merge(aircraft_id(icao), rec)
        return n

    def poll(self, get: Callable[..., str], now: float) -> dict[str, Any]:
        """One adsb.lol cycle: all military, plus the next civil hubs. A failing call is skipped, never fatal."""
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
        with self.lock:
            self.a = {k: r for k, r in self.a.items() if now - r[4] <= r[9]}
            if len(self.a) > flags.AIRCRAFT_MAX:              # keep every military aircraft, then the freshest civil
                mil = {k: r for k, r in self.a.items() if r[5] != 0}
                civ = sorted(((k, r) for k, r in self.a.items() if r[5] == 0), key=lambda kv: -kv[1][4])[:max(0, flags.AIRCRAFT_MAX - len(mil))]
                self.a = {**mil, **dict(civ)}
            self.tracks.prune(self.a, now)

    def snapshot(self, now: float) -> dict[str, Any]:
        with self.lock:
            self.prune(now)
            rows, counts = [], {"civil": 0, "military": 0}
            for aid, (lat, lon, hdg, spd, seen, cls, call, typ, alt, _ttl) in self.a.items():
                counts["civil" if cls == 0 else "military"] += 1
                row = [aid, round(lon, 3), round(lat, 3), round(hdg), round(spd), cls, int(seen), call, typ, alt]
                while len(row) > 7 and row[-1] in ("", -1):
                    row.pop()
                rows.append(row)
        return {"v": 1, "as_of": iso(datetime.fromtimestamp(now, tz=timezone.utc)), "n": len(rows), "counts": counts,
                "classes": ["civil", "military", "tanker", "surveillance", "airlift", "fighter"],
                "f": ["id", "lon", "lat", "hdg", "spd", "cls", "ts", "callsign", "type", "alt"], "rows": rows}
