"""
The stream service (``newsroom live ais``, systemd unit ``ohmega-ais``) — everything that has to be always on:

  * the aisstream websocket (world boxes by default; permessage-deflate) feeding the daily gate counter AND the live vessel board;
  * extra free AIS sources merged into the same board by MMSI: Finnish Digitraffic (REST) and Norwegian Kystverket (NMEA over TCP);
  * the aircraft sources: OpenSky (the whole world in one call) and adsb.lol (all military + a few civil hubs per cycle) merged into
    the sky board by ICAO address, freshest position winning;
  * every ``SNAPSHOT_SECONDS`` the world ``points`` (compact real positions for the far-out glow; the old ``density`` grid is still written, unused), the object ``tiles/`` (+ index) and ``summary`` (and, until the site no longer
    needs them, the full ``vessels`` / ``aircraft``: ``flags.PUBLISH_FULL_SNAPSHOT``) to the public Storage bucket,
    every ``memory.flags.SAMPLE_SECONDS`` a count of what is on the boards per cell / area / class, folded into an hourly mean on disk
    (live memory, ``live/memory/``: baselines and anomalies are computed from it by the timer runner's tick),
    every ``flows.flags.CYCLE_SECONDS`` the lane tracker folds the vessel board into ship-lane counts (``flows/``: aggregates only),
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
from algent_backend.flows.tracker import LaneTracker
from algent_backend.maritime import store as maritime_store
from algent_backend.maritime.profile import ProfileBook
from algent_backend.maritime.watch import Watch

from . import flags, headlines, points, snapshots, store, tiles
from .ais_memory import Coverage, StaticMemory
from .board import VesselBoard
from .contracts import iso
from .feeds import ais
from .ingest import digitraffic, kystverket, opensky
from .memory import Sampler
from .sky import SkyBoard


def build_docs(board: VesselBoard, sky: SkyBoard, now: float, *, tracks: bool = False, sampler: Sampler | None = None) -> dict[str, Any]:
    """The documents of one cycle: vessels, aircraft, summary (and the trail shards when ``tracks``). Also refreshes the local
    ``gates_now`` document the timer runner's summary reads. Everything is built from the boards' current state."""
    at = datetime.fromtimestamp(now, tz=timezone.utc)
    vessels, gates = board.snapshot(now)
    aircraft = sky.snapshot(now)
    if sampler is not None:           # live memory: an hourly mean of what is on the boards (live/memory/); counts only, never raises
        sampler.observe(vessels, aircraft, board.coverage.seen.keys(), now)
    store.write_doc("gates_now", {"as_of": iso(at), "gates": gates})
    docs: dict[str, Any] = {"vessels": vessels, "aircraft": aircraft,
                            "summary": headlines.build(at, extra_fresh={"ships": vessels["as_of"], "aircraft": aircraft["as_of"]})}
    docs.update(tiles.build(vessels, aircraft))
    docs["points"] = points.build(vessels, aircraft)
    if not flags.PUBLISH_FULL_SNAPSHOT:
        del docs["vessels"], docs["aircraft"]
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


def _watch_cycle(watch: Watch, board: VesselBoard, now: float) -> dict[str, Any] | None:
    """Maritime behaviour memory: fold the board into the profile book and run due detector passes. Never raises."""
    try:
        return watch.cycle(board, now)
    except Exception as exc:  # noqa: BLE001 - behaviour memory must never cost the stream a snapshot
        store.record_status("maritime", error=f"{type(exc).__name__}: {str(exc)[:160]}")
        return None


def _save_profiles(doc: dict[str, Any]) -> None:
    try:
        ProfileBook.write(maritime_store.profiles_path(), doc)
    except Exception as exc:  # noqa: BLE001 - a failed save only costs a restart some memory
        store.record_status("maritime", error=f"save: {type(exc).__name__}: {str(exc)[:120]}")


def _flows_cycle(flows: LaneTracker, board: VesselBoard, now: float) -> dict[str, Any] | None:
    """Lane tracking: fold the board's ships into the lane counts when a pass is due. Never raises."""
    try:
        return flows.cycle(board, now)
    except Exception as exc:  # noqa: BLE001 - lane counts must never cost the stream a snapshot
        store.record_status("flows", error=f"{type(exc).__name__}: {str(exc)[:160]}")
        return None


def _save_flows(docs: dict[str, Any]) -> None:
    try:
        LaneTracker.write(docs)
    except Exception as exc:  # noqa: BLE001 - a failed save only costs a restart some counts
        store.record_status("flows", error=f"save: {type(exc).__name__}: {str(exc)[:120]}")


async def _cycle_loop(board: VesselBoard, sky: SkyBoard, stop_at: float | None,
                      get: Callable[..., str] = polite_http.get, sampler: Sampler | None = None, watch: Watch | None = None,
                      flows: LaneTracker | None = None) -> None:
    last_tracks = 0.0
    while stop_at is None or time.monotonic() < stop_at:
        started = time.time()
        try:
            await asyncio.to_thread(sky.poll, get, started)
            with_tracks = started - last_tracks >= flags.PERSIST_SECONDS
            docs = build_docs(board, sky, time.time(), tracks=with_tracks, sampler=sampler)
            if watch is not None:
                _watch_cycle(watch, board, time.time())
                if watch.persist_due(started):
                    await asyncio.to_thread(_save_profiles, watch.document(started))
            if flows is not None:
                _flows_cycle(flows, board, time.time())
                if flows.persist_due(started):
                    await asyncio.to_thread(_save_flows, flows.snapshot(started))
            res = await asyncio.to_thread(snapshots.publish, docs)
            if with_tracks:
                last_tracks = started
                await asyncio.to_thread(_save_memory, dict(board.static.m), dict(board.coverage.seen))
            store.record_status("stream", last_ok=iso(datetime.now(timezone.utc)), error="",
                                note=f"{docs['density']['layers']['vessels']['n']} vessels, {docs['density']['layers']['aircraft']['n']} aircraft; upload {res.get('assets', 0)} new, {len(res.get('failed', []))} failed")
        except Exception as exc:  # noqa: BLE001 - the service outlives a bad cycle
            store.record_status("stream", error=f"{type(exc).__name__}: {str(exc)[:160]}")
        await asyncio.sleep(max(1.0, flags.SNAPSHOT_SECONDS - (time.time() - started)))


async def run(key: str = "", *, max_seconds: float | None = None) -> None:
    """Run every source (the websocket only with an AIS key) and the snapshot cycle together."""
    board = VesselBoard(static=StaticMemory.load(_static_path()), coverage=Coverage.load(_coverage_path()))
    sky = SkyBoard()
    watch = Watch.load()
    board.watch = watch
    stop_at = None if max_seconds is None else time.monotonic() + max_seconds
    tasks = [_cycle_loop(board, sky, stop_at, sampler=Sampler(), watch=watch, flows=LaneTracker.load())]
    if key:
        tasks.append(ais.serve(key, max_seconds=max_seconds, counter=ais.load_counter(), board=board))
    if flags.OPENSKY_ENABLED:
        tasks.append(opensky.poll_loop(sky, stop_at))
    if flags.DIGITRAFFIC_ENABLED:
        tasks.append(digitraffic.poll_loop(board, stop_at))
    if flags.KYSTVERKET_ENABLED:
        tasks.append(kystverket.serve(board, stop_at))
    await asyncio.gather(*tasks)
