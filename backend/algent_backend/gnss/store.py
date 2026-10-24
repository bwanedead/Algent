"""
GNSS store on disk — an append-only log of hourly tallies, plus derived daily files.

    <root>/hours/<YYYY-MM-DD>.jsonl   one line per hourly sample: {"t", "probes", "aircraft", "cells": {cell: [observations, degraded]}}; never rewritten
    <root>/days/<YYYY-MM-DD>.json     a CLOSED day's summed tally (a cache of the hours; rebuilt if missing)
    <root>/zones/<YYYY-MM-DD>.json    the day's published zones (ours and GPSJam's); rewritten while the day is open
    <root>/status.json                per source: last good run, last error
    <root>/since.json                 per source: the first day anything was collected (the "collecting since" of every figure)

Root: ``ALGENT_GNSS_STORE`` or ``gnss_store``. Hour lines hold counts only, never per-aircraft records, and GPSJam's file is stored only as its top-band
cells; ``prune`` bounds the folder by age (``flags.HOURS_KEEP_DAYS``, ``ZONES_FULL_DAYS``, ``KEEP_DAYS``). A zone's per-source constants (the coverage
note, "watching since") are not repeated on every stored zone: ``save_zones`` strips them and ``load_zones`` puts them back.
"""

from __future__ import annotations

import json
import os
from datetime import UTC, date, datetime, timedelta
from pathlib import Path

from . import flags
from .contracts import COVERAGE
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
_LEAN = ("coverage_note", "baseline_since")


def save_zones(day: str, doc: dict) -> None:
    lean = {**doc, **{k: [{f: v for f, v in z.items() if f not in _LEAN} for z in doc.get(k, [])] for k in ("zones", "gpsjam")}}
    _write_json(root() / "zones" / f"{day}.json", lean)


def load_zones(day: str) -> dict:
    doc = _read_json(root() / "zones" / f"{day}.json", {})
    if not isinstance(doc, dict):
        return {}
    since = str(doc.get("baseline_since", ""))
    for key, src in (("zones", "ohmega_adsb"), ("gpsjam", "gpsjam")):
        for z in doc.get(key, []):
            z.setdefault("coverage_note", COVERAGE[src])
            z.setdefault("baseline_since", since if src == "ohmega_adsb" else "")
    return doc


def zone_days() -> list[str]:
    d = root() / "zones"
    return sorted(p.stem for p in d.glob("*.json")) if d.is_dir() else []


# -- status / since ------------------------------------------------------------
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


def prior_days(day: str, n: int) -> list[str]:
    d0 = date.fromisoformat(day)
    return [(d0 - timedelta(days=k)).isoformat() for k in range(1, n + 1)]


# -- retention ---------------------------------------------------------------------------------------
def size_mb() -> float:
    return sum(p.stat().st_size for p in root().rglob("*") if p.is_file()) / 1_000_000 if root().is_dir() else 0.0


def prune(today: date | None = None) -> dict[str, int]:
    """The store's retention (the registry names this function), applied after every pass. A closed day's summed tally is written to ``days/`` BEFORE its
    hour lines are dropped (the baseline reads the sums, so nothing it needs is lost); an old zone file loses GPSJam's cells and keeps ours. Never raises."""
    today = today or date.today()
    day = lambda n: (today - timedelta(days=n)).isoformat()  # noqa: E731
    dropped = compacted = 0
    for d in hour_days():
        if d < day(flags.HOURS_KEEP_DAYS):
            day_tally(d, today)                                 # persist the closed day's sums first
            if (root() / "days" / f"{d}.json").is_file():
                (root() / "hours" / f"{d}.jsonl").unlink(missing_ok=True)
                dropped += 1
    for sub, ext in (("days", "json"), ("hours", "jsonl"), ("zones", "json")):
        for p in (root() / sub).glob(f"*.{ext}") if (root() / sub).is_dir() else ():
            if p.stem < day(flags.KEEP_DAYS):
                p.unlink(missing_ok=True)
                dropped += 1
    for d in zone_days():
        if d < day(flags.ZONES_FULL_DAYS) and (doc := load_zones(d)).get("gpsjam"):
            save_zones(d, {**doc, "gpsjam": []})
            compacted += 1
    return {"dropped": dropped, "compacted": compacted}
