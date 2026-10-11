"""
Ships — OUR OWN daily chokepoint transit counts from aisstream.io's live AIS websocket (free key ``ALGENT_AISSTREAM_KEY``,
https://aisstream.io/authenticate). A long-running service (``newsroom live ais``), not a timer job.

``GateCounter`` is the pure core: feed it AIS messages and it counts a vessel (unique MMSI) once per UTC day per gate
when two successive positions fall on opposite sides of the gate line, inside the gate's box; tankers are the vessels
whose static data says ship type 80-89. The service wraps it with the websocket, periodic flushes of the running day
into the instruments store (``live_ais_<gate>_transits`` / ``..._tanker_transits``, completed days only) and
state persistence so a restart loses nothing. IMF PortWatch stays the reference series; this one is current to the day.

HONEST LIMIT: terrestrial AIS receivers only hear ships near volunteer stations; coverage differs by strait and a
ship with its transponder off is invisible. Read these as our counts, comparable with themselves over time.
"""

from __future__ import annotations

import asyncio
import json
import os
import time
from datetime import date, datetime, timezone
from typing import Any

from algent_backend.instruments.live_series import ais_ids

from .. import flags, store
from ..contracts import Feed, FeedResult, NeedsKey, Stat
from ..regions import GATES, Gate, inside

WS_URL = "wss://stream.aisstream.io/v0/stream"
SIGNUP = "https://aisstream.io/authenticate"
KEY_ENV = "ALGENT_AISSTREAM_KEY"
TANKER_TYPES = range(80, 90)


def _side(g: Gate, lat: float, lon: float) -> int:
    """Which side of the gate line the point is on: +1, -1 (0 exactly on it)."""
    cross = (g.b[1] - g.a[1]) * (lat - g.a[0]) - (g.b[0] - g.a[0]) * (lon - g.a[1])
    return (cross > 0) - (cross < 0)


class GateCounter:
    def __init__(self) -> None:
        self.day = ""
        self.crossed: dict[str, set[int]] = {g.slug: set() for g in GATES}
        self.types: dict[int, int] = {}
        self.last: dict[tuple[str, int], tuple[int, float]] = {}      # (gate, mmsi) -> (side, seen at)

    def to_json(self) -> dict[str, Any]:
        return {"day": self.day, "crossed": {k: sorted(v) for k, v in self.crossed.items()},
                "types": {str(k): v for k, v in self.types.items() if k in self._interesting()}}

    @classmethod
    def from_json(cls, doc: dict[str, Any]) -> "GateCounter":
        c = cls()
        c.day = doc.get("day", "")
        c.crossed.update({k: set(v) for k, v in doc.get("crossed", {}).items() if k in c.crossed})
        c.types = {int(k): v for k, v in doc.get("types", {}).items()}
        return c

    def _interesting(self) -> set[int]:
        return set().union(*self.crossed.values())

    def message(self, msg: dict[str, Any], now: float, today: str) -> None:
        if today != self.day:                                  # the UTC day turned: counts restart
            self.day, self.crossed = today, {g.slug: set() for g in GATES}
        body = msg.get("Message") or {}
        meta = msg.get("MetaData") or {}
        mmsi = meta.get("MMSI") or (body.get("PositionReport") or body.get("ShipStaticData") or {}).get("UserID")
        if not mmsi:
            return
        static = body.get("ShipStaticData")
        if static and static.get("Type") is not None:
            self.types[int(mmsi)] = int(static["Type"])
            return
        pos = body.get("PositionReport") or body.get("StandardClassBPositionReport")
        lat = meta.get("latitude", (pos or {}).get("Latitude"))
        lon = meta.get("longitude", (pos or {}).get("Longitude"))
        if pos is None or lat is None or lon is None:
            return
        for g in GATES:
            if not inside(g.box, lat, lon):
                continue
            side = _side(g, lat, lon)
            prev = self.last.get((g.slug, int(mmsi)))
            if side and prev and prev[0] != side and now - prev[1] <= flags.AIS_TRACK_TTL_S:
                self.crossed[g.slug].add(int(mmsi))
            if side:
                self.last[(g.slug, int(mmsi))] = (side, now)

    def prune(self, now: float) -> None:
        self.last = {k: v for k, v in self.last.items() if now - v[1] <= flags.AIS_TRACK_TTL_S}

    def stats(self) -> list[Stat]:
        out = []
        for g in GATES:
            total_id, tanker_id = ais_ids(g.slug)
            ships = self.crossed[g.slug]
            out += [Stat(series_id=total_id, value=len(ships), mode="set"),
                    Stat(series_id=tanker_id, value=sum(self.types.get(m) in TANKER_TYPES for m in ships), mode="set")]
        return out


def subscription(key: str) -> str:
    boxes = [[[g.box[0], g.box[1]], [g.box[2], g.box[3]]] for g in GATES]
    return json.dumps({"APIKey": key, "BoundingBoxes": boxes,
                       "FilterMessageTypes": ["PositionReport", "ShipStaticData", "StandardClassBPositionReport"]})


def _state_path():
    return store.root() / "ais_state.json"


def flush(counter: GateCounter, today: date) -> dict[str, int]:
    """Write the running day to the instruments pipeline and persist the counter."""
    res = store.apply_stats(counter.stats(), today, owner="ais")
    store._write(_state_path(), counter.to_json())
    store.record_status("ais", last_ok=datetime.now(timezone.utc).isoformat(timespec="seconds"), error="",
                        note="; ".join(f"{g.slug} {len(counter.crossed[g.slug])}" for g in GATES))
    return res


def load_counter() -> GateCounter:
    return GateCounter.from_json(store._read(_state_path(), {}))


async def serve(key: str, *, max_seconds: float | None = None) -> None:
    """Listen forever (or ``max_seconds``): reconnect with backoff, flush every ``AIS_FLUSH_SECONDS``."""
    import aiohttp

    counter, delay, started = load_counter(), 5.0, time.monotonic()
    last_flush = 0.0
    while max_seconds is None or time.monotonic() - started < max_seconds:
        try:
            async with aiohttp.ClientSession() as session, session.ws_connect(WS_URL, heartbeat=30) as ws:
                await ws.send_str(subscription(key))
                delay = 5.0
                async for raw in ws:
                    if raw.type != aiohttp.WSMsgType.TEXT:
                        break
                    now = time.time()
                    msg = json.loads(raw.data)
                    if msg.get("error"):
                        raise RuntimeError(str(msg["error"])[:120])
                    counter.message(msg, now, datetime.now(timezone.utc).date().isoformat())
                    if now - last_flush >= flags.AIS_FLUSH_SECONDS:
                        counter.prune(now)
                        flush(counter, datetime.now(timezone.utc).date())
                        last_flush = now
                    if max_seconds is not None and time.monotonic() - started >= max_seconds:
                        break
        except Exception as exc:  # noqa: BLE001 - the service outlives any one connection
            store.record_status("ais", error=f"{type(exc).__name__}: {str(exc)[:120]}")
        flush(counter, datetime.now(timezone.utc).date())
        await asyncio.sleep(delay)
        delay = min(delay * 2, flags.AIS_RECONNECT_MAX_S)


def run_service(max_seconds: float | None = None) -> int:
    key = os.environ.get(KEY_ENV, "")
    if not key:
        store.record_status("ais", needs=FEED.needs(), error="")
        print(FEED.needs())
        return 2
    asyncio.run(serve(key, max_seconds=max_seconds))
    return 0


def _no_timer(_ctx) -> FeedResult:
    raise NeedsKey("the AIS feed is a service: run `newsroom live ais` (systemd unit ohmega-ais)")


# Registered for status/doctor only; ``fetch`` is never called by the timer runner (see runner.TIMER_FEEDS).
FEED = Feed("ais", "Ships (chokepoint counts)", "aisstream.io", "https://aisstream.io/", _no_timer,
            key_env=KEY_ENV, signup_url=SIGNUP)
