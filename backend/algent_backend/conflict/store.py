"""
Conflict store on disk — an append-only event log sharded by event date, plus small state files.

    <root>/events/<YYYY-MM-DD>.jsonl   one ConflictEvent per line, never rewritten (a repeated id is ignored)
    <root>/status.json                 per source: last good fetch, last error, counts
    <root>/cursor.json                 GDELT: the stamp of the last 15-minute file read
    <root>/since.json                  per source: the day we first stored anything from it (the "collecting since" of every count)
    <root>/published.json              per shard: lines the publisher has consumed and rows it sent to the site database

Root: ``ALGENT_CONFLICT_STORE`` or ``conflict_store``. Shards keep a 15-minute collector from ever loading the whole history: a run reads only
the few shards near the events it is about to add.
"""

from __future__ import annotations

import json
import os
from datetime import UTC, date, datetime, timedelta
from pathlib import Path

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
                fh.write("\n".join(e.model_dump_json() for e in write) + "\n")
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


def published() -> dict[str, dict[str, int]]:
    """Per shard day: ``lines`` consumed by the publisher and ``sent`` rows actually pushed (the per-day cap counts the latter)."""
    return {k: {"lines": int(v.get("lines", 0)), "sent": int(v.get("sent", 0))} for k, v in _read_json("published.json").items() if isinstance(v, dict)}


def save_published(marks: dict[str, dict[str, int]]) -> None:
    _write_json("published.json", marks)


def lines_after(day: str, n: int) -> list[ConflictEvent]:
    out = []
    for line in _lines(day)[n:]:
        try:
            out.append(ConflictEvent.model_validate_json(line))
        except ValueError:
            continue
    return out
