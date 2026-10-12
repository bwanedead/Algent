"""
Norwegian Coastal Administration (Kystverket) open AIS — raw NMEA over TCP, keyless, NLOD licence ("Contains data under the
Norwegian licence for open government data (NLOD) distributed by the Norwegian Coastal Administration").

One long-lived socket to ``flags.KYSTVERKET_HOST:PORT``; every ``!AIVDM`` line is decoded (``nmea.py``) and merged into the ship
board by MMSI. Reconnects with backoff; a failed connection is recorded in the status file and retried.

HONEST LIMIT: the open stream covers the Norwegian economic zone and the Svalbard / Jan Mayen protection zones, and Kystverket
describes it as excluding small fishing and leisure craft. Where it adds ships is the Norwegian coast, the Norwegian Sea and the
Arctic approaches that aisstream's volunteer receivers hear thinly.
"""

from __future__ import annotations

import asyncio
import time
from typing import Any

from .. import flags, store
from .nmea import Decoder

CREDIT = "Norwegian Coastal Administration, NLOD"


def apply(board: Any, msg: dict[str, Any], now: float) -> bool:
    """Merge one decoded message into the board."""
    if msg["kind"] == "static":
        board.static.put(msg["mmsi"], msg.get("type"), msg.get("name"), msg.get("dest"), now)
        return False
    return board.report(msg["mmsi"], msg["lat"], msg["lon"], now, heading=msg["heading"], cog=msg["cog"], sog=msg["sog"],
                        name=msg.get("name"), ship_type=msg.get("type"))


async def serve(board: Any, stop_at: float | None) -> None:
    decoder, delay, stored, lines = Decoder(), 5.0, 0, 0
    while stop_at is None or time.monotonic() < stop_at:
        try:
            reader, writer = await asyncio.wait_for(asyncio.open_connection(flags.KYSTVERKET_HOST, flags.KYSTVERKET_PORT), 30)
            delay = 5.0
            try:
                while stop_at is None or time.monotonic() < stop_at:
                    raw = await asyncio.wait_for(reader.readline(), 120)
                    if not raw:
                        break
                    lines += 1
                    msg = decoder.feed(raw.decode("ascii", "replace"))
                    if msg:
                        stored += apply(board, msg, time.time())
                    if lines % 5000 == 0:
                        store.record_status("kystverket", last_ok=time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()), error="",
                                            note=f"{lines} lines, {stored} positions stored")
            finally:
                writer.close()
        except Exception as exc:  # noqa: BLE001
            store.record_status("kystverket", error=f"{type(exc).__name__}: {str(exc)[:160]}")
        await asyncio.sleep(delay)
        delay = min(delay * 2, flags.AIS_RECONNECT_MAX_S)
