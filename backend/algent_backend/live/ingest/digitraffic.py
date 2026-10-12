"""
Finnish Digitraffic marine AIS (Fintraffic) — keyless REST, licence CC 4.0 BY (credit: "Fintraffic / digitraffic.fi").

``/api/ais/v1/locations`` is a GeoJSON snapshot of every vessel the Finnish coastal receivers hold (~800, Gulf of Finland, Baltic,
Bothnian Sea); ``/api/ais/v1/vessels`` is their metadata (name, ship type, destination), fetched less often. Polled politely
(one request a minute, the ``Digitraffic-User`` header they ask for). Positions merge into the ship board by MMSI.

HONEST LIMIT: Finnish waters only. It adds ships (and types/names) where aisstream's volunteer receivers are thin, not open ocean.
"""

from __future__ import annotations

import asyncio
import json
import time
from typing import Any, Callable

from .. import flags, store

BASE = "https://meri.digitraffic.fi/api/ais/v1"
HEADERS = {"Digitraffic-User": "ohmega-live/1.0", "Accept-Encoding": "gzip"}
META_EVERY_S = 900
CREDIT = "Fintraffic / digitraffic.fi, CC 4.0 BY"


def parse_locations(text: str) -> list[dict[str, Any]]:
    """GeoJSON features -> ``[{mmsi, lat, lon, sog, cog, heading, ts}]`` (``ts`` unix seconds; the report's own time)."""
    out = []
    for f in json.loads(text).get("features") or []:
        p, g = f.get("properties") or {}, (f.get("geometry") or {}).get("coordinates") or []
        ts = p.get("timestampExternal")
        if len(g) < 2 or not f.get("mmsi") or not isinstance(ts, (int, float)):
            continue
        out.append({"mmsi": int(f["mmsi"]), "lon": g[0], "lat": g[1], "sog": p.get("sog"), "cog": p.get("cog"),
                    "heading": p.get("heading"), "ts": ts / 1000.0})
    return out


def parse_vessels(text: str) -> list[dict[str, Any]]:
    """Metadata rows -> ``[{mmsi, name, type, dest}]``."""
    return [{"mmsi": int(v["mmsi"]), "name": v.get("name"), "type": v.get("shipType"), "dest": v.get("destination")}
            for v in json.loads(text) if isinstance(v, dict) and v.get("mmsi")]


def _fetch(path: str) -> str:
    import httpx

    r = httpx.get(f"{BASE}/{path}", headers=HEADERS, timeout=60)
    r.raise_for_status()
    return r.text


def apply(board: Any, locations: list[dict[str, Any]], vessels: list[dict[str, Any]] | None, now: float) -> int:
    """Merge one fetch into the ship board; returns how many positions it stored."""
    for v in vessels or []:
        board.static.put(v["mmsi"], v["type"], v["name"], v["dest"], now)
    return sum(board.report(r["mmsi"], r["lat"], r["lon"], min(r["ts"], now), heading=r["heading"], cog=r["cog"], sog=r["sog"])
               for r in locations)


async def poll_loop(board: Any, stop_at: float | None, fetch: Callable[[str], str] = _fetch) -> None:
    """Every ``DIGITRAFFIC_INTERVAL_S``: fetch off the loop, merge on it (the board is single-threaded by design)."""
    last_meta = 0.0
    while stop_at is None or time.monotonic() < stop_at:
        try:
            with_meta = time.time() - last_meta >= META_EVERY_S
            locs = parse_locations(await asyncio.to_thread(fetch, "locations"))
            meta = parse_vessels(await asyncio.to_thread(fetch, "vessels")) if with_meta else None
            if with_meta:
                last_meta = time.time()
            n = apply(board, locs, meta, time.time())
            store.record_status("digitraffic", last_ok=time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()), error="",
                                note=f"{len(locs)} vessels, {n} stored")
        except Exception as exc:  # noqa: BLE001
            store.record_status("digitraffic", error=f"{type(exc).__name__}: {str(exc)[:160]}")
        await asyncio.sleep(flags.DIGITRAFFIC_INTERVAL_S)
