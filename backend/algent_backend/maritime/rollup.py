"""
Maritime daily rollups and retention - "only store the compressions" (docs/architecture/database-budget.md, "Ship data").

Raw ship data on this server comes in three shapes, and only one of them is unbounded:

* ``profiles.json.gz``   the profile book: per-vessel identity + at most ``SAMPLES_MAX`` hourly samples, expiring ``PROFILE_KEEP_S`` after a ship
                         was last heard. BOUNDED already (tens of MB at ``PROFILE_MAX`` vessels).
* ``events.json``        the current picture: the last ``RETAIN_DAYS`` days, at most ``EVENTS_MAX`` events. BOUNDED.
* ``log.jsonl``          append-only: a full event (evidence points, detail) every time an event opens or changes state. UNBOUNDED, and a line is
                         ~2-3 KB, so a busy stream makes it the file that grows without limit. This is the retention target.

What the detectors need (derived, not guessed): a detector reads the profile book (4 days), the activity grid (``ACTIVITY_KEEP_H``, 4 days) and
``events.json`` (``RETAIN_DAYS``). NOTHING reads ``log.jsonl`` back except people. So its raw lines are kept for ``LOG_KEEP_DAYS`` =
``RETAIN_DAYS`` (the same window as the picture, so a log line is never newer than something still shown) and older ones are summarised and dropped.

A daily summary (``<maritime_store>/daily/<YYYY-MM-DD>.json.gz``, a few KB) holds, per day:

    zones     per named zone/chokepoint: unique ships by class, ships underway, median speed (knots), samples seen   (from the profile book)
    events    opened that day: total, by kind, by area, by outcome; AIS gaps per area                              (from the log)
    notable   up to ``NOTABLE_MAX`` events (sanctioned, or confidence >= ``NOTABLE_CONFIDENCE``) in compact rows
    tracks    up to ``TRACK_VESSELS`` flagged vessels' evidence points (<= ``TRACK_POINTS`` each) - the only positions kept long term

The summaries are in the nightly ``data_backup`` mirror and are never deleted: ~5-10 KB a day, ~3 MB a year.

Safe against the always-on stream service appending to the log: the log is renamed aside (the writer opens-appends-closes per line, so it simply
creates a fresh file), processed line by line (never loaded whole), and the recent lines are appended back. A crash leaves ``log.jsonl.work``
and the next run resumes from it.
"""

from __future__ import annotations

import gzip
import heapq
import json
import os
import statistics
from collections import Counter
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

from . import flags, store
from .profile import MOVING_KN, ProfileBook

#: Raw log lines are kept this many days (see the module doc: the picture's own window).
LOG_KEEP_DAYS = flags.RETAIN_DAYS
NOTABLE_MAX = 30
NOTABLE_CONFIDENCE = 0.8
TRACK_VESSELS = 12
TRACK_POINTS = 24
SUMMARY = "ohmega.maritime-day/1"


def daily_dir() -> Path:
    return store.root() / "daily"


def _day_start(day: str) -> float:
    return datetime.strptime(day, "%Y-%m-%d").replace(tzinfo=timezone.utc).timestamp()


def read_day(day: str) -> dict[str, Any]:
    try:
        with gzip.open(daily_dir() / f"{day}.json.gz", "rt", encoding="utf-8") as fh:
            doc = json.load(fh)
        return doc if isinstance(doc, dict) else {}
    except (OSError, ValueError, EOFError):
        return {}


def write_day(day: str, doc: dict[str, Any]) -> Path:
    path = daily_dir() / f"{day}.json.gz"
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".tmp")
    tmp.write_bytes(gzip.compress(json.dumps(doc, ensure_ascii=False, separators=(",", ":")).encode("utf-8"), compresslevel=9, mtime=0))
    os.replace(tmp, path)
    return path


# ── zones, from the profile book ─────────────────────────────────────────────────────────────────
def zones_of_day(book: ProfileBook, day: str) -> dict[str, Any]:
    """Per named zone (chokepoints and regions): the ships whose samples fell inside it that UTC day."""
    from algent_backend.live.classify import VESSEL_CLASSES, vessel_class
    from algent_backend.live.memory.areas import areas_at

    t0 = _day_start(day)
    ships: dict[str, dict[int, str]] = {}
    moving: dict[str, set[int]] = {}
    speeds: dict[str, list[float]] = {}
    seen: Counter[str] = Counter()
    labels: dict[str, str] = {}
    for p in book.profiles.values():
        cls = VESSEL_CLASSES[vessel_class(p.ship_type)]
        for ts, lat, lon, sog in p.points():
            if not t0 <= ts < t0 + 86400:
                continue
            for a in areas_at(lat, lon):
                if a.kind == "fire":
                    continue
                labels[a.id] = a.label
                ships.setdefault(a.id, {})[p.mmsi] = cls
                seen[a.id] += 1
                if sog >= MOVING_KN:
                    moving.setdefault(a.id, set()).add(p.mmsi)
                    speeds.setdefault(a.id, []).append(sog)
    out: dict[str, Any] = {}
    for zid in sorted(ships):
        by_class = Counter(ships[zid].values())
        out[zid] = {"label": labels[zid], "ships": len(ships[zid]), "by_class": dict(sorted(by_class.items())), "underway": len(moving.get(zid, ())),
                    "median_kn": round(statistics.median(speeds[zid]), 1) if speeds.get(zid) else None, "samples": seen[zid]}
    return out


# ── events, from the log ─────────────────────────────────────────────────────────────────────────
class DayAcc:
    """What the old log lines of one day add up to. Each line is counted once and then dropped, so merging into a summary never double counts."""

    def __init__(self) -> None:
        self.opened = 0
        self.by_kind: Counter[str] = Counter()
        self.by_area: Counter[str] = Counter()
        self.gaps_by_area: Counter[str] = Counter()
        self.outcomes: Counter[str] = Counter()
        self.notable: list[tuple[float, str, dict[str, Any]]] = []      # min-heap of (confidence, id, row)
        self.tracks: list[tuple[float, str, dict[str, Any]]] = []

    def add(self, line: dict[str, Any]) -> None:
        e, kind = line.get("e") or {}, line.get("event", "")
        if not e:
            return
        if kind == "open":
            self.opened += 1
            self.by_kind[e.get("kind", "?")] += 1
            area = e.get("area") or "open ocean"
            self.by_area[area] += 1
            if e.get("kind") == "ais_gap":
                self.gaps_by_area[area] += 1
        else:
            self.outcomes[kind] += 1
        conf = float(e.get("confidence") or 0)
        if e.get("kind") == "sanctioned" or conf >= NOTABLE_CONFIDENCE:
            row = {k: e.get(k) for k in ("id", "kind", "mmsi", "name", "imo", "flag", "area", "started_at", "ended_at", "confidence")}
            row["summary"] = str(e.get("summary", ""))[:160]
            _push(self.notable, NOTABLE_MAX, (conf, str(e.get("id")), row))
        pts = [list(p[:4]) for p in (e.get("evidence") or [])[-TRACK_POINTS:] if isinstance(p, list) and len(p) >= 4]
        if len(pts) >= 2:
            _push(self.tracks, TRACK_VESSELS, (conf, str(e.get("id")), {"id": e.get("id"), "mmsi": e.get("mmsi"), "name": e.get("name", ""),
                                                                        "kind": e.get("kind"), "pts": pts}))


def _push(heap: list, cap: int, item: tuple) -> None:
    if any(h[1] == item[1] for h in heap):
        heap[:] = [h for h in heap if h[1] != item[1]]
        heapq.heapify(heap)
    if len(heap) < cap:
        heapq.heappush(heap, item)
    elif item > heap[0]:
        heapq.heapreplace(heap, item)


def merge_events(day: str, acc: DayAcc) -> dict[str, Any]:
    """Fold an accumulator into the day's summary (counts add; notable / tracks keep the strongest)."""
    doc = read_day(day) or {"schema": SUMMARY, "day": day}
    ev = doc.setdefault("events", {"opened": 0, "by_kind": {}, "by_area": {}, "gaps_by_area": {}, "outcomes": {}})
    ev["opened"] += acc.opened
    for key, counter in (("by_kind", acc.by_kind), ("by_area", acc.by_area), ("gaps_by_area", acc.gaps_by_area), ("outcomes", acc.outcomes)):
        merged = Counter(ev.get(key, {}))
        merged.update(counter)
        ev[key] = dict(sorted(merged.items(), key=lambda kv: (-kv[1], kv[0])))
    for key, heap, cap in (("notable", acc.notable, NOTABLE_MAX), ("tracks", acc.tracks, TRACK_VESSELS)):
        pool = {r["id"]: r for r in doc.get(key, []) if r.get("id")}
        pool.update({item[2]["id"]: item[2] for item in heap if item[2].get("id")})
        doc[key] = list(pool.values())[-cap:] if key == "tracks" else sorted(pool.values(), key=lambda r: -float(r.get("confidence") or 0))[:cap]
    return doc


def compact_log(*, now: float, apply: bool, keep_days: int = LOG_KEEP_DAYS, path: Path | None = None) -> dict[str, Any]:
    """Summarise and drop log lines older than ``keep_days``. Dry run (``apply=False``) reads the log and reports; it renames and writes nothing."""
    path = path or store.root() / "log.jsonl"
    work = path.with_suffix(path.suffix + ".work")
    kept_file = path.with_suffix(path.suffix + ".kept")
    cutoff = (datetime.fromtimestamp(now, tz=timezone.utc) - timedelta(days=keep_days)).isoformat(timespec="seconds")
    out: dict[str, Any] = {"cutoff": cutoff, "lines": 0, "kept": 0, "summarised": 0, "bytes_before": 0, "bytes_after": 0, "days": []}
    if work.exists():                        # a crashed earlier run: resume from what it set aside
        source = work
    elif path.exists():
        source = path
        if apply:
            os.replace(path, work)           # the writer opens-appends-closes each line, so it just starts a fresh log.jsonl
            source = work
    else:
        return {**out, "note": "no log"}
    out["bytes_before"] = source.stat().st_size + (path.stat().st_size if source is work and path.exists() else 0)
    accs: dict[str, DayAcc] = {}
    kept_bytes = 0
    with source.open("r", encoding="utf-8") as src, (kept_file.open("w", encoding="utf-8", newline="\n") if apply else open(os.devnull, "w")) as keep:
        for raw in src:
            out["lines"] += 1
            try:
                obj = json.loads(raw)
            except ValueError:
                continue                     # a torn line carries nothing
            if str(obj.get("at", "")) >= cutoff:
                keep.write(raw if raw.endswith("\n") else raw + "\n")
                out["kept"] += 1
                kept_bytes += len(raw)
            else:
                day = str((obj.get("e") or {}).get("started_at") or obj.get("at", ""))[:10]
                if len(day) == 10:
                    accs.setdefault(day, DayAcc()).add(obj)
                    out["summarised"] += 1
    out["days"] = sorted(accs)
    if apply:
        for day, acc in accs.items():
            write_day(day, merge_events(day, acc))
        with path.open("a", encoding="utf-8", newline="\n") as dst, kept_file.open("r", encoding="utf-8") as kept:
            for chunk in iter(lambda: kept.read(1 << 20), ""):
                dst.write(chunk)
        kept_file.unlink(missing_ok=True)
        if source == work:
            work.unlink(missing_ok=True)
    out["bytes_after"] = kept_bytes if not apply else (path.stat().st_size if path.exists() else 0)
    return out


def run(*, now: float | None = None, apply: bool = False, days_back: int = 3) -> dict[str, Any]:
    """The daily job: zone summaries for the recent complete days (the profile book holds ~4 days), then the log compaction."""
    now = now or datetime.now(timezone.utc).timestamp()
    today = datetime.fromtimestamp(now, tz=timezone.utc).date()
    out: dict[str, Any] = {"zones": []}
    book = ProfileBook.load(store.profiles_path())
    if book.profiles:
        for back in range(1, days_back + 1):
            day = (today - timedelta(days=back)).isoformat()
            zones = zones_of_day(book, day)
            if zones and apply:
                doc = read_day(day) or {"schema": SUMMARY, "day": day}
                doc["zones"] = zones
                write_day(day, doc)
            if zones:
                out["zones"].append(day)
    out["log"] = compact_log(now=now, apply=apply)
    return out


def store_report() -> dict[str, Any]:
    """Size of every file in the maritime store (what to look at when the directory is big)."""
    root = store.root()
    files = sorted(((p.stat().st_size, p.relative_to(root).as_posix()) for p in root.rglob("*") if p.is_file()), reverse=True) if root.is_dir() else []
    return {"root": str(root), "total_bytes": sum(s for s, _ in files), "files": [{"path": n, "bytes": s} for s, n in files[:15]],
            "daily_summaries": len(list(daily_dir().glob("*.json.gz"))) if daily_dir().is_dir() else 0}
