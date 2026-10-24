"""
Maritime store on disk. Root: ``ALGENT_MARITIME_STORE`` or ``maritime_store`` (like the sanctions and live stores; the stream service
writes it, the timer runner reads and publishes it).

    profiles.json.gz   the profile book (``profile.py``): per-vessel identity, last position, thin history; bounded, replaced atomically
    state.json         the detectors' open work: slow encounters and dwell trackers (``watch.py``), small
    events.json        the CURRENT picture: behaviour events of the last ``RETAIN_DAYS`` days, by id (replaced atomically)
    log.jsonl          append-only: one compact line per transition (open / ended / unresolved), never per touch (eventlog.py; the long record)
    log_ledger.json    which transitions are already written (eventlog.Ledger), so a re-found event is not logged twice
    published.json    the watermark of the last publish to the site database and, per event, the signature + time of what was last sent
"""

from __future__ import annotations

import json
import os
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

from . import eventlog, flags
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


def _essence(e: BehaviourEvent) -> dict[str, Any]:
    return e.model_dump(exclude={"updated_at"})


def upsert(events: list[BehaviourEvent], now: float) -> dict[str, int]:
    """Merge detector output into the current picture: new ids are added, a changed event is replaced, events that ended more than
    ``RETAIN_DAYS`` ago and the oldest ENDED events beyond ``EVENTS_MAX`` are dropped (a going event is never the one cut). The long record
    (``eventlog``) gets a compact line per first open and per end, never per touch; an event the picture let go of but whose end is on
    record is not added back when a detector finds it again. Returns ``{"new", "changed", "kept"}``."""
    at = iso(now)
    cur = read_current()
    ledger = eventlog.Ledger.load(root() / eventlog.LEDGER)
    horizon = iso((datetime.fromtimestamp(now, tz=timezone.utc) - timedelta(days=flags.RETAIN_DAYS)).timestamp())
    new = changed = 0
    for e in events:
        old = cur.get(e.id)
        if old is None and ((e.ended_at is not None and e.ended_at < horizon) or ledger.closed(e.id)):
            continue                                   # past the picture's window, or already closed and let go: not news
        if old is not None and _essence(old) == _essence(e):
            continue
        e = e.model_copy(update={"updated_at": at})
        if old is None:
            new += 1
            if ledger.admit(e.id, e.kind, e.mmsi, "open", now, born_closed=e.state != "ongoing"):
                eventlog.append(root(), eventlog.compact(e.model_dump(), "open", at))
        else:
            changed += 1
            if old.state != e.state and e.state != "ongoing" and ledger.admit(e.id, e.kind, e.mmsi, e.state, now):
                eventlog.append(root(), eventlog.compact(e.model_dump(), e.state, at))
        cur[e.id] = e
    kept = [e for e in cur.values() if e.ended_at is None or e.ended_at >= horizon]
    kept.sort(key=lambda e: (e.ended_at is None, e.last_seen or e.started_at), reverse=True)
    kept = kept[:flags.EVENTS_MAX]
    if new or changed or len(kept) != len(cur) or not (root() / "events.json").exists():
        _write(root() / "events.json", {"as_of": at, "events": [e.model_dump() for e in kept]})
    ledger.save(root() / eventlog.LEDGER, now)
    return {"new": new, "changed": changed, "kept": len(kept)}


# ── publish watermark ────────────────────────────────────────────────────────────────────────────
def published_at() -> str:
    return str(_read(root() / "published.json", {}).get("at", ""))


def published_sent() -> dict[str, list[str]]:
    """``{event id: [signature, sent_at]}``: what the site table was last given for each event (see ``publish.signature``)."""
    sent = _read(root() / "published.json", {}).get("sent", {})
    return sent if isinstance(sent, dict) else {}


def save_published(at: str, sent: dict[str, list[str]] | None = None) -> None:
    """Record the watermark and (when given) the per-event record of what was sent; ids no longer in the picture are dropped."""
    alive = read_current()
    keep = {k: v for k, v in (sent if sent is not None else published_sent()).items() if k in alive}
    _write(root() / "published.json", {"at": at, "sent": keep})
