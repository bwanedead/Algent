"""
Collector — one hourly pass: sample ADS-B around the probe points, tally, append, rebuild today's zones, and (once a day) read GPSJam.

Each source is isolated: a probe that does not answer is skipped (the hour records how many did), GPSJam being down leaves our own zones untouched
and the other way round. Memory stays small: only the few fields the derivation needs are kept of each aircraft, and tallies hold counts, not records.
"""

from __future__ import annotations

import json
from collections.abc import Callable, Iterable
from datetime import UTC, date, datetime, timedelta
from typing import Any

from algent_backend.polite_http import SourceError, get, stream_lines

from . import derive, flags, gpsjam, store, zones
from .contracts import Zone

URL = "https://api.adsb.lol/v2/point/{lat}/{lon}/{radius}"
_KEEP = ("hex", "type", "lat", "lon", "nac_p", "version", "alt_baro")


def sample(fetch: Callable[..., str] = get) -> tuple[derive.Tally, int, int]:
    """(per-cell tally, probes answered, usable aircraft) over every probe point; overlapping circles count an aircraft once."""
    seen: dict[str, dict[str, Any]] = {}
    answered = 0
    for _name, lat, lon in flags.PROBES:
        try:
            body = json.loads(fetch(URL.format(lat=lat, lon=lon, radius=flags.RADIUS_NM)))
        except (SourceError, ValueError):
            continue
        answered += 1
        for ac in body.get("ac", []):
            if derive.usable(ac):
                seen.setdefault(ac["hex"], {k: ac.get(k) for k in _KEEP})
    return derive.tally(seen.values()), answered, len(seen)


def doc_for(day: str, ours: list[Zone], theirs: list[Zone], *, today: date) -> dict[str, Any]:
    zones.cross_check(ours, theirs)
    return {"date": day, "generated_at": store.now_iso(), "samples": store.samples(day), "baseline_days": store.baseline_days(today),
            "baseline_since": store.since().get("ohmega_adsb", ""),
            "zones": [z.model_dump() for z in ours], "gpsjam": [z.model_dump() for z in theirs]}


def rebuild(day: str, today: date) -> dict[str, Any]:
    prior = store.load_zones(day)
    theirs = [Zone.model_validate(z) for z in prior.get("gpsjam", [])]
    doc = doc_for(day, zones.build(day, today=today), theirs, today=today)
    store.save_zones(day, doc)
    return doc


def read_gpsjam(today: date, lines: Callable[[str], Iterable[str]]) -> dict[str, Any]:
    day, theirs = gpsjam.fetch(today, lines=lines)
    ours = [Zone.model_validate(z) for z in store.load_zones(day).get("zones", [])]
    store.save_zones(day, doc_for(day, ours, theirs, today=today))
    store.save_status("gpsjam", last_ok=store.now_iso(), last_error="", last_day=day, cells=len(theirs))
    return {"day": day, "cells": len(theirs)}


def run(*, now: datetime | None = None, fetch: Callable[..., str] = get, lines: Callable[[str], Iterable[str]] = stream_lines,
        with_gpsjam: bool = True) -> dict[str, Any]:
    now = now or datetime.now(UTC)
    today = now.date()
    out: dict[str, Any] = {"as_of": now.isoformat(timespec="seconds")}
    try:
        cells, answered, n = sample(fetch)
        if not answered:
            raise SourceError("no ADS-B probe answered")
        store.append_hour(today.isoformat(), cells, probes=answered, aircraft=n, t=now.isoformat(timespec="seconds"))
        days = [today.isoformat()] + ([(today - timedelta(days=1)).isoformat()] if now.hour < 2 else [])
        docs = {d: rebuild(d, today) for d in days}
        store.save_status("ohmega_adsb", last_ok=store.now_iso(), last_error="", probes=answered, aircraft=n)
        out["adsb"] = {"status": "ok", "probes": answered, "of": len(flags.PROBES), "aircraft": n, "cells": len(cells),
                       "zones": len(docs[today.isoformat()]["zones"])}
    except (SourceError, ValueError, OSError) as exc:
        out["adsb"] = {"status": "error", "error": f"{type(exc).__name__}: {str(exc)[:200]}"}
        store.save_status("ohmega_adsb", last_error=out["adsb"]["error"], last_error_at=store.now_iso())
    if with_gpsjam and store.load_status().get("gpsjam", {}).get("last_day", "") < (today - timedelta(days=1)).isoformat():
        try:
            out["gpsjam"] = {"status": "ok", **read_gpsjam(today, lines)}
        except (SourceError, ValueError, OSError) as exc:
            out["gpsjam"] = {"status": "error", "error": f"{type(exc).__name__}: {str(exc)[:200]}"}
            store.save_status("gpsjam", last_error=out["gpsjam"]["error"], last_error_at=store.now_iso())
    return out
