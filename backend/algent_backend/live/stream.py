"""
The stream service (``newsroom live ais``, systemd unit ``ohmega-ais``) — everything that has to be always on:

  * the aisstream websocket (world boxes by default; permessage-deflate) feeding the daily gate counter AND the live vessel board;
  * extra free AIS sources merged into the same board by MMSI: Finnish Digitraffic (REST) and Norwegian Kystverket (NMEA over TCP);
  * the aircraft sources: OpenSky (the whole world in one call) and adsb.lol (all military + a few civil hubs per cycle) merged into
    the sky board by ICAO address, freshest position winning;
  * every ``SNAPSHOT_SECONDS`` one compact JSON per layer (``vessels``, ``aircraft``, ``summary``) to the public Storage bucket,
    and every ``PERSIST_SECONDS`` the short-trail shards (``tracks/v<k>``, ``tracks/a<k>``), the receiver-coverage grid and the local
    saves of the MMSI static memory (so a restart does not forget every ship's type).

State is bounded (boards expire and cap themselves) and nothing per-object is stored beyond the live board, its short trails and
the small static memory. A failed cycle is logged to the status file and the next one runs; the service outlives any single failure.
"""

from __future__ import annotations

import asyncio
import time
from datetime import datetime, timezone
from typing import Any, Callable

from algent_backend import polite_http

from . import flags, headlines, snapshots, store
from .ais_memory import Coverage, StaticMemory
from .board import VesselBoard
from .contracts import iso
from .feeds import ais
from .ingest import digitraffic, kystverket, opensky
from .sky import SkyBoard


def build_docs(board: VesselBoard, sky: SkyBoard, now: float, *, tracks: bool = False) -> dict[str, Any]:
    """The documents of one cycle: vessels, aircraft, summary (and the trail shards when ``tracks``). Also refreshes the local
    ``gates_now`` document the timer runner's summary reads. Everything is built from the boards' current state."""
    at = datetime.fromtimestamp(now, tz=timezone.utc)
    vessels, gates = board.snapshot(now)
    aircraft = sky.snapshot(now)
    store.write_doc("gates_now", {"as_of": iso(at), "gates": gates})
    docs: dict[str, Any] = {"vessels": vessels, "aircraft": aircraft,
                            "summary": headlines.build(at, extra_fresh={"ships": vessels["as_of"], "aircraft": aircraft["as_of"]})}
    if tracks:
        docs["coverage"] = board.coverage.document(vessels["as_of"], now)
        for k in range(flags.TRACK_SHARDS):
            docs[f"tracks/v{k}"] = {"as_of": vessels["as_of"], "t": board.tracks.shard(k, flags.TRACK_SHARDS)}
        with sky.lock:         # worker threads (OpenSky, adsb.lol) add to these trails
            for k in range(flags.AIR_TRACK_SHARDS):
                docs[f"tracks/a{k}"] = {"as_of": aircraft["as_of"], "t": sky.tracks.shard(k, flags.AIR_TRACK_SHARDS)}
    return docs


def _static_path():
    return store.root() / "ais_static.json"


def _coverage_path():
    return store.root() / "ais_coverage.json"


def _save_memory(static: dict, seen: dict) -> None:
    """Write the static memory and coverage grid copies taken on the loop thread (the boards are single-threaded; the write is not)."""
    try:
        StaticMemory.write(_static_path(), static)
        Coverage.write(_coverage_path(), seen)
    except Exception as exc:  # noqa: BLE001 - a failed save only costs a slower restart
        store.record_status("stream_memory", error=f"{type(exc).__name__}: {str(exc)[:120]}")


async def _cycle_loop(board: VesselBoard, sky: SkyBoard, stop_at: float | None,
                      get: Callable[..., str] = polite_http.get) -> None:
    last_tracks = 0.0
    while stop_at is None or time.monotonic() < stop_at:
        started = time.time()
        try:
            await asyncio.to_thread(sky.poll, get, started)
            with_tracks = started - last_tracks >= flags.PERSIST_SECONDS
            docs = build_docs(board, sky, time.time(), tracks=with_tracks)
            res = await asyncio.to_thread(snapshots.publish, docs)
            if with_tracks:
                last_tracks = started
                await asyncio.to_thread(_save_memory, dict(board.static.m), dict(board.coverage.seen))
            store.record_status("stream", last_ok=iso(datetime.now(timezone.utc)), error="",
                                note=f"{docs['vessels']['n']} vessels, {docs['aircraft']['n']} aircraft; upload {res.get('assets', 0)} new, {len(res.get('failed', []))} failed")
        except Exception as exc:  # noqa: BLE001 - the service outlives a bad cycle
            store.record_status("stream", error=f"{type(exc).__name__}: {str(exc)[:160]}")
        await asyncio.sleep(max(1.0, flags.SNAPSHOT_SECONDS - (time.time() - started)))


async def run(key: str = "", *, max_seconds: float | None = None) -> None:
    """Run every source (the websocket only with an AIS key) and the snapshot cycle together."""
    board = VesselBoard(static=StaticMemory.load(_static_path()), coverage=Coverage.load(_coverage_path()))
    sky = SkyBoard()
    stop_at = None if max_seconds is None else time.monotonic() + max_seconds
    tasks = [_cycle_loop(board, sky, stop_at)]
    if key:
        tasks.append(ais.serve(key, max_seconds=max_seconds, counter=ais.load_counter(), board=board))
    if flags.OPENSKY_ENABLED:
        tasks.append(opensky.poll_loop(sky, stop_at))
    if flags.DIGITRAFFIC_ENABLED:
        tasks.append(digitraffic.poll_loop(board, stop_at))
    if flags.KYSTVERKET_ENABLED:
        tasks.append(kystverket.serve(board, stop_at))
    await asyncio.gather(*tasks)
