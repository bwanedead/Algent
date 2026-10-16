"""
Hour documents — the raw hourly detail memory keeps on the SERVER's disk for ``HOUR_KEEP_DAYS`` (60) days and then deletes.

    <live_store>/memory/hours/<YYYY-MM-DDTHH>.<source>.json.gz

One file per (hour, source): ``stream`` (ships and aircraft, from the always-on service), ``firms`` (fires), ``ioda`` and
``usgs`` (outage and quake counts, from the timer runs). Each process writes only its own file, so the service and the timers
never overwrite one another. Inside: ``s`` maps a series (``ship.tanker``) to its values by place - cells as two parallel
integer lists (delta-coded cell ids, values in 1/8 units) and named areas / the world as a small dict. An hour's value is the MEAN
over the hour's samples. Nothing per-object is ever stored. Only compact rollups of this leave the server (see ``daily.py``).
"""

from __future__ import annotations

import gzip
import json
import os
import re
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Iterable

from .. import store
from . import flags

SCALE = 8                       # stored units per object for cell values
Values = dict[str, dict[int | str, float]]       # series -> place -> mean value that hour

_NAME = re.compile(r"^(\d{4}-\d{2}-\d{2}T\d{2})\.([a-z0-9_]+)\.json\.gz$")


def root() -> Path:
    return store.root() / "memory"


def hours_dir() -> Path:
    return root() / "hours"


def hour_of(ts: float) -> int:
    return int(ts // 3600)


def stamp(hour: int) -> str:
    return datetime.fromtimestamp(hour * 3600, tz=timezone.utc).strftime("%Y-%m-%dT%H")


def iso_hour(hour: int) -> str:
    return datetime.fromtimestamp(hour * 3600, tz=timezone.utc).isoformat(timespec="seconds")


def hour_from_stamp(text: str) -> int:
    return int(datetime.strptime(text, "%Y-%m-%dT%H").replace(tzinfo=timezone.utc).timestamp() // 3600)


def day_of(hour: int) -> int:
    return hour // 24


def day_hours(day: int) -> range:
    return range(day * 24, day * 24 + 24)


# ── codec ───────────────────────────────────────────────────────────────────────────────────────
def encode(values: Values) -> dict[str, Any]:
    out: dict[str, Any] = {}
    for series, places in values.items():
        cells = sorted((p, v) for p, v in places.items() if isinstance(p, int) and v > 0)
        prev, deltas = 0, []
        for c, _v in cells:
            deltas.append(c - prev)
            prev = c
        rec: dict[str, Any] = {}
        if cells:
            rec["c"], rec["x"] = deltas, [max(1, round(v * SCALE)) for _c, v in cells]
        named = {p: round(v, 2) for p, v in places.items() if isinstance(p, str)}
        if named:
            rec["a"] = named
        if rec:
            out[series] = rec
    return out


def decode(doc: dict[str, Any]) -> Values:
    out: Values = {}
    for series, rec in doc.items():
        places: dict[int | str, float] = dict(rec.get("a", {}))
        cell = 0
        for d, x in zip(rec.get("c", []), rec.get("x", []), strict=True):
            cell += d
            places[cell] = x / SCALE
        out[series] = places
    return out


# ── files ───────────────────────────────────────────────────────────────────────────────────────
def write_hour(hour: int, source: str, samples: int, values: Values) -> Path:
    path = hours_dir() / f"{stamp(hour)}.{source}.json.gz"
    path.parent.mkdir(parents=True, exist_ok=True)
    body = json.dumps({"v": 1, "hour": hour, "source": source, "n": samples, "s": encode(values)}, separators=(",", ":")).encode()
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_bytes(gzip.compress(body, compresslevel=6, mtime=0))
    os.replace(tmp, path)
    return path


@dataclass
class Hour:
    hour: int
    samples: dict[str, int] = field(default_factory=dict)         # source -> samples behind it
    values: Values = field(default_factory=dict)

    def observed(self, source: str, need: int = 1) -> bool:
        return self.samples.get(source, 0) >= need


def read_hour(hour: int) -> Hour:
    """Every source's file for the hour, merged. A missing or damaged file is simply absent (the hour is unobserved for it)."""
    out = Hour(hour)
    for path in sorted(hours_dir().glob(f"{stamp(hour)}.*.json.gz")) if hours_dir().is_dir() else []:
        try:
            doc = json.loads(gzip.decompress(path.read_bytes()))
        except (OSError, ValueError, EOFError):
            continue
        out.samples[doc.get("source", "?")] = int(doc.get("n", 0))
        out.values.update(decode(doc.get("s", {})))
    return out


def stored_hours() -> list[int]:
    """Epoch hours that have at least one file, ascending."""
    seen = {hour_from_stamp(m.group(1)) for p in (hours_dir().glob("*.json.gz") if hours_dir().is_dir() else []) if (m := _NAME.match(p.name))}
    return sorted(seen)


def prune(now: float) -> int:
    """Delete hour files older than ``HOUR_KEEP_DAYS``; returns how many."""
    horizon = (datetime.fromtimestamp(now, tz=timezone.utc) - timedelta(days=flags.HOUR_KEEP_DAYS)).strftime("%Y-%m-%dT%H")
    gone = 0
    for p in list(hours_dir().glob("*.json.gz")) if hours_dir().is_dir() else []:
        m = _NAME.match(p.name)
        if m and m.group(1) < horizon:
            p.unlink(missing_ok=True)
            gone += 1
    return gone


def disk_bytes() -> int:
    return sum(p.stat().st_size for p in hours_dir().glob("*.json.gz")) if hours_dir().is_dir() else 0


def mean_over(hours: Iterable[Hour], series: str, place: int | str, source: str, need: int) -> tuple[float, int]:
    """(mean value, observed hours) of a place's series across hours whose ``source`` file holds enough samples."""
    vals = [h.values.get(series, {}).get(place, 0.0) for h in hours if h.observed(source, need)]
    return (sum(vals) / len(vals) if vals else 0.0), len(vals)
