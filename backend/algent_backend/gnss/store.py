"""
GNSS store on disk — an append-only log of hourly tallies, plus derived daily files.

    <root>/hours/<YYYY-MM-DD>.jsonl   one line per hourly sample: {"t", "probes", "aircraft", "cells": {cell: [observations, degraded]}}; never rewritten
    <root>/days/<YYYY-MM-DD>.json     a CLOSED day's summed tally (a cache of the hours; rebuilt if missing)
    <root>/zones/<YYYY-MM-DD>.json    the day's published zones (ours and GPSJam's); rewritten while the day is open
    <root>/status.json                per source: last good run, last error
    <root>/since.json                 per source: the first day anything was collected (the "collecting since" of every figure)

Root: ``ALGENT_GNSS_STORE`` or ``gnss_store``. Hour lines hold counts only, never per-aircraft records.
"""

from __future__ import annotations

import json
import os
from datetime import UTC, date, datetime, timedelta
from pathlib import Path

from .derive import Tally

_ENV = "ALGENT_GNSS_STORE"


def root() -> Path:
    return Path(os.environ.get(_ENV) or "gnss_store")


def now_iso() -> str:
    return datetime.now(UTC).isoformat(timespec="seconds")


def _write_json(path: Path, doc: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(doc, separators=(",", ":"), ensure_ascii=False), encoding="utf-8", newline="\n")
    tmp.replace(path)


def _read_json(path: Path, default: object) -> object:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return default


# -- hours / days ----------------------------------------------------------------------------------
def append_hour(day: str, cells: Tally, *, probes: int, aircraft: int, t: str | None = None) -> None:
    p = root() / "hours" / f"{day}.jsonl"
    p.parent.mkdir(parents=True, exist_ok=True)
    line = json.dumps({"t": t or now_iso(), "probes": probes, "aircraft": aircraft, "cells": cells}, separators=(",", ":"))
    with p.open("a", encoding="utf-8", newline="\n") as fh:
        fh.write(line + "\n")
    note_since("ohmega_adsb", day)


def hour_lines(day: str) -> list[dict]:
    out = []
    try:
        lines = (root() / "hours" / f"{day}.jsonl").read_text(encoding="utf-8").splitlines()
    except OSError:
        return out
    for line in lines:
        try:
            out.append(json.loads(line))
        except ValueError:
            continue                                        # a torn line must not hide the rest
    return out


def day_tally(day: str, today: date | None = None) -> Tally:
    """The day's summed per-cell tally; a closed day is cached to ``days/``."""
    today = today or date.today()
    cache = root() / "days" / f"{day}.json"
    closed = day < today.isoformat()
    if closed and (hit := _read_json(cache, None)) is not None:
        return hit                                          # type: ignore[return-value]
    out: Tally = {}
    for h in hour_lines(day):
        for cell, (n, bad) in h.get("cells", {}).items():
            row = out.setdefault(cell, [0, 0])
            row[0] += n
            row[1] += bad
    if closed and out:
        _write_json(cache, out)
    return out


def hour_days() -> list[str]:
    d = root() / "hours"
    return sorted(p.stem for p in d.glob("*.jsonl")) if d.is_dir() else []


def samples(day: str) -> int:
    return len(hour_lines(day))


# -- zones -----------------------------------------------------------------------------------------
def save_zones(day: str, doc: dict) -> None:
    _write_json(root() / "zones" / f"{day}.json", doc)


def load_zones(day: str) -> dict:
    doc = _read_json(root() / "zones" / f"{day}.json", {})
    return doc if isinstance(doc, dict) else {}


def zone_days() -> list[str]:
    d = root() / "zones"
    return sorted(p.stem for p in d.glob("*.json")) if d.is_dir() else []


# -- status / since / publish watermark ------------------------------------------------------------
def load_status() -> dict[str, dict]:
    doc = _read_json(root() / "status.json", {})
    return doc if isinstance(doc, dict) else {}


def save_status(source: str, **fields: object) -> None:
    st = load_status()
    st[source] = {**st.get(source, {}), **fields}
    _write_json(root() / "status.json", st)


def since() -> dict[str, str]:
    doc = _read_json(root() / "since.json", {})
    return {k: str(v) for k, v in doc.items()} if isinstance(doc, dict) else {}


def note_since(source: str, day: str) -> None:
    s = since()
    if source not in s:
        _write_json(root() / "since.json", {**s, source: day})


def baseline_days(today: date | None = None) -> int:
    """Closed days of hourly samples on file: how much history the flags stand on."""
    today = (today or date.today()).isoformat()
    return sum(1 for d in hour_days() if d < today)


def published_days() -> dict[str, str]:
    doc = _read_json(root() / "published.json", {})
    return {k: str(v) for k, v in doc.items()} if isinstance(doc, dict) else {}


def save_published(marks: dict[str, str]) -> None:
    _write_json(root() / "published.json", marks)


def prior_days(day: str, n: int) -> list[str]:
    d0 = date.fromisoformat(day)
    return [(d0 - timedelta(days=k)).isoformat() for k in range(1, n + 1)]
