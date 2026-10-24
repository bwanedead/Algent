"""
Conflict store on disk — an append-only event log sharded by event date, plus small state files.

    <root>/events/<YYYY-MM-DD>.jsonl   one ConflictEvent per line, never rewritten (a repeated id is ignored)
    <root>/status.json                 per source: last good fetch, last error, counts
    <root>/cursor.json                 GDELT: the stamp of the last 15-minute file read
    <root>/since.json                  per source: the day we first stored anything from it (the "collecting since" of every count)

Root: ``ALGENT_CONFLICT_STORE`` or ``conflict_store``. Shards keep a 15-minute collector from ever loading the whole history: a run reads only
the few shards near the events it is about to add. ONLY events are stored (never a source's raw file) and ``prune`` bounds the folder by age and by
size (``flags.KEEP_DAYS_*``, ``flags.MAX_STORE_MB``): the registry's budget for this store is these numbers.
"""

from __future__ import annotations

import json
import os
from collections.abc import Iterator
from datetime import UTC, date, datetime, timedelta
from pathlib import Path

from . import flags
from .contracts import ConflictEvent

_ENV = "ALGENT_CONFLICT_STORE"


def root() -> Path:
    return Path(os.environ.get(_ENV) or "conflict_store")


def now_iso() -> str:
    return datetime.now(UTC).isoformat(timespec="seconds")


def _write_json(name: str, doc: object) -> None:
    path = root() / name
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(doc, indent=1, ensure_ascii=False), encoding="utf-8", newline="\n")
    tmp.replace(path)


def _read_json(name: str) -> dict:
    try:
        doc = json.loads((root() / name).read_text(encoding="utf-8"))
        return doc if isinstance(doc, dict) else {}
    except (OSError, ValueError):
        return {}


# -- events --------------------------------------------------------------------------------------
def shard_path(day: str) -> Path:
    return root() / "events" / f"{day}.jsonl"


def shard_days() -> list[str]:
    d = root() / "events"
    return sorted(p.stem for p in d.glob("*.jsonl")) if d.is_dir() else []


def _lines(day: str) -> list[str]:
    try:
        return [x for x in shard_path(day).read_text(encoding="utf-8").splitlines() if x.strip()]
    except OSError:
        return []


def shard(day: str) -> list[ConflictEvent]:
    out = []
    for line in _lines(day):
        try:
            out.append(ConflictEvent.model_validate_json(line))
        except ValueError:
            continue                                        # a torn line must not hide the rest
    return out


def known_ids(days: set[str]) -> set[str]:
    return {e.id for d in days for e in shard(d)}


def append(new: list[ConflictEvent]) -> list[ConflictEvent]:
    """Append the events whose id is not on file in their shard; returns the ones written."""
    fresh: list[ConflictEvent] = []
    by_day: dict[str, list[ConflictEvent]] = {}
    for e in new:
        by_day.setdefault(e.date, []).append(e)
    for day, rows in by_day.items():
        have = {e.id for e in shard(day)}
        write = [e for e in rows if e.id not in have and not have.add(e.id)]
        if write:
            p = shard_path(day)
            p.parent.mkdir(parents=True, exist_ok=True)
            with p.open("a", encoding="utf-8", newline="\n") as fh:
                fh.write("\n".join(e.stored() for e in write) + "\n")
            fresh += write
    for src in {e.source for e in fresh}:
        note_since(src)
    return fresh


def events(days: int, today: date | None = None, *, source: str | None = None) -> list[ConflictEvent]:
    """Events dated within the last ``days`` days (newest shard first inside the list is not guaranteed; sort at the caller)."""
    today = today or date.today()
    floor = (today - timedelta(days=days)).isoformat()
    out: list[ConflictEvent] = []
    for d in shard_days():
        if floor <= d <= today.isoformat():
            out += [e for e in shard(d) if not source or e.source == source]
    return out


def line_count() -> int:
    return sum(len(_lines(d)) for d in shard_days())


# -- status / cursor / since / publish watermark ---------------------------------------------------
def load_status() -> dict[str, dict]:
    return _read_json("status.json")


def save_status(source: str, **fields: object) -> None:
    st = load_status()
    st[source] = {**st.get(source, {}), **fields}
    _write_json("status.json", st)


def load_cursor() -> dict:
    return _read_json("cursor.json")


def save_cursor(**fields: object) -> None:
    _write_json("cursor.json", {**load_cursor(), **fields})


def since() -> dict[str, str]:
    return {k: str(v) for k, v in _read_json("since.json").items()}


def note_since(source: str) -> None:
    s = since()
    if source not in s:
        _write_json("since.json", {**s, source: date.today().isoformat()})


def collecting_since() -> str:
    """The first day any source stored anything: the date every count on the site is "since"."""
    s = since()
    return min(s.values()) if s else ""


# -- streaming reads and retention -----------------------------------------------------------------
def iter_events(days: int, today: date | None = None) -> Iterator[ConflictEvent]:
    """Events dated within the last ``days`` days, one at a time (a publisher that keeps only the strongest few never holds a shard)."""
    today = today or date.today()
    floor, top = (today - timedelta(days=days)).isoformat(), today.isoformat()
    for d in shard_days():
        if not floor <= d <= top:
            continue
        try:
            with shard_path(d).open(encoding="utf-8") as fh:
                for line in fh:
                    try:
                        yield ConflictEvent.model_validate_json(line)
                    except ValueError:
                        continue                            # a torn line must not hide the rest
        except OSError:
            continue


def day_counts(days: int, today: date | None = None) -> dict[str, dict[str, int]]:
    """Per event date: ``{"events": n, "machine": n, "curated": n}`` (the rest are reports) over the whole shard (a count never limited by what a document carries). Reads lines, not models."""
    today = today or date.today()
    floor, top = (today - timedelta(days=days)).isoformat(), today.isoformat()
    out: dict[str, dict[str, int]] = {}
    for d in shard_days():
        if floor <= d <= top:
            lines = _lines(d)
            out[d] = {"events": len(lines), "machine": sum(1 for x in lines if '"coding":"machine"' in x), "curated": sum(1 for x in lines if '"coding":"curated"' in x)}
    return out


def _size(p: Path) -> int:
    try:
        return p.stat().st_size
    except OSError:
        return 0


def size_mb() -> float:
    return sum(_size(shard_path(d)) for d in shard_days()) / 1_000_000


def prune(today: date | None = None) -> dict[str, int]:
    """The store's retention (the registry names this function). Drops event shards older than the window (machine-coded GDELT: ``KEEP_DAYS_MACHINE``;
    anything else: ``KEEP_DAYS_OTHER``), then, if the folder is still over ``MAX_STORE_MB``, the oldest shards until it is not. A shard is one event date, so a
    day holds events of every source; it counts as machine-coded only when every event in it is. Never raises: a file that will not delete stays for the next pass."""
    today = today or date.today()
    machine_floor = (today - timedelta(days=flags.KEEP_DAYS_MACHINE)).isoformat()
    other_floor = (today - timedelta(days=flags.KEEP_DAYS_OTHER)).isoformat()
    dropped = freed = 0

    def drop(day: str) -> None:
        nonlocal dropped, freed
        p = shard_path(day)
        n = _size(p)
        try:
            p.unlink()
        except OSError:
            return
        dropped, freed = dropped + 1, freed + n

    for day in shard_days():
        if day < other_floor or (day < machine_floor and _is_machine_only(day)):
            drop(day)
    over = size_mb() - flags.MAX_STORE_MB
    for day in shard_days():                                   # oldest first
        if over <= 0:
            break
        before = _size(shard_path(day)) / 1_000_000
        drop(day)
        over -= before
    return {"dropped": dropped, "freed_kb": freed // 1000}


def _is_machine_only(day: str) -> bool:
    return all(e.coding == "machine" for e in shard(day))

