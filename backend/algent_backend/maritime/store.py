"""
Maritime store on disk. Root: ``ALGENT_MARITIME_STORE`` or ``maritime_store`` (like the sanctions and live stores; the stream service
writes it, the timer runner reads and publishes it).

    profiles.json.gz   the profile book (``profile.py``): per-vessel identity, last position, thin history; bounded, replaced atomically
    state.json         the detectors' open work: slow encounters and dwell trackers (``watch.py``), small
    events.json        the CURRENT picture: behaviour events of the last ``RETAIN_DAYS`` days, by id (replaced atomically)
    log.jsonl          append-only: a line each time an event is first seen or changes state (the long record)
    published.json    the watermark of the last publish to the site database
"""

from __future__ import annotations

import json
import os
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

from . import flags
from .contracts import BehaviourEvent, iso

_ENV = "ALGENT_MARITIME_STORE"


def root() -> Path:
    return Path(os.environ.get(_ENV) or "maritime_store")


def profiles_path() -> Path:
    return root() / "profiles.json.gz"


def _read(path: Path, default: Any) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return default


def _write(path: Path, doc: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(doc, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
    os.replace(tmp, path)


def read_state() -> dict[str, Any]:
    return _read(root() / "state.json", {})


def write_state(doc: dict[str, Any]) -> None:
    _write(root() / "state.json", doc)


# ── events ───────────────────────────────────────────────────────────────────────────────────────
def read_current() -> dict[str, BehaviourEvent]:
    """The current events by id (empty before the first detector pass)."""
    out: dict[str, BehaviourEvent] = {}
    for d in _read(root() / "events.json", {}).get("events", []):
        try:
            e = BehaviourEvent.model_validate(d)
        except ValueError:
            continue
        out[e.id] = e
    return out


def _log(event: str, e: BehaviourEvent, at: str) -> None:
    path = root() / "log.jsonl"
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8", newline="\n") as fh:
        fh.write(json.dumps({"event": event, "at": at, "e": e.model_dump()}, ensure_ascii=False, separators=(",", ":")) + "\n")


def _essence(e: BehaviourEvent) -> dict[str, Any]:
    return e.model_dump(exclude={"updated_at"})


def upsert(events: list[BehaviourEvent], now: float) -> dict[str, int]:
    """Merge detector output into the current picture: new ids are added (and logged), a changed event is replaced (state changes
    are logged), events that ended more than ``RETAIN_DAYS`` ago and the oldest beyond ``EVENTS_MAX`` are dropped.
    Returns ``{"new", "changed", "kept"}``."""
    at = iso(now)
    cur = read_current()
    new = changed = 0
    for e in events:
        old = cur.get(e.id)
        if old is not None and _essence(old) == _essence(e):
            continue
        e = e.model_copy(update={"updated_at": at})
        if old is None:
            new += 1
            _log("open", e, at)
        else:
            changed += 1
            if old.state != e.state:
                _log(e.state, e, at)
        cur[e.id] = e
    horizon = iso((datetime.fromtimestamp(now, tz=timezone.utc) - timedelta(days=flags.RETAIN_DAYS)).timestamp())
    kept = [e for e in cur.values() if e.ended_at is None or e.ended_at >= horizon]
    kept.sort(key=lambda e: e.last_seen or e.started_at, reverse=True)
    kept = kept[:flags.EVENTS_MAX]
    if new or changed or len(kept) != len(cur) or not (root() / "events.json").exists():
        _write(root() / "events.json", {"as_of": at, "events": [e.model_dump() for e in kept]})
    return {"new": new, "changed": changed, "kept": len(kept)}


# ── publish watermark ────────────────────────────────────────────────────────────────────────────
def published_at() -> str:
    return str(_read(root() / "published.json", {}).get("at", ""))


def save_published(at: str) -> None:
    _write(root() / "published.json", {"at": at})
