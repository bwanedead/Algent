"""
The maritime long record: ``log.jsonl`` holds ONE compact line per state TRANSITION of an event, never the event itself.

    {"id","kind","state","mmsi","imo","name","ship_class","at","lat","lon","area","confidence"}      state: open | ended | unresolved

"ongoing" is not a transition and is never written; a full event (evidence, detail, rationale) lives in ``events.json`` while it is current,
and long-term positions live in the daily summaries. Measured before this existed: 1.7 GB in ~6 days (~250 k lines a day, ~1.9 KB each).

Why the old log was so chatty, and the guard (``Ledger``, ``log_ledger.json``): the picture is a bounded cache (``EVENTS_MAX``), so an event
that fell out was found again by its detector on the next pass and logged "open" again, and an event whose state flapped
(a sanctioned sighting going stale and fresh around ``2 * DETECT_SECONDS + 900``) logged every flip. The ledger remembers, per event id, which
transitions were already written (an id writes ``open`` once and one terminal line once), and per vessel + kind when it last wrote an ``open``
(``flags.LOG_COOLDOWN_S``). It is bounded by ``RETAIN_DAYS`` and is also what the store uses to avoid re-adding an event it already closed.
"""

from __future__ import annotations

import json
import os
from datetime import datetime
from pathlib import Path
from typing import Any

from . import flags

LOG = "log.jsonl"
LEDGER = "log_ledger.json"
STATES = ("open", "ended", "unresolved")
_TERMINAL = {"ended": "e", "unresolved": "u"}


def epoch(at: str) -> float:
    try:
        return datetime.fromisoformat(at).timestamp()
    except ValueError:
        return 0.0


def compact(e: dict[str, Any], state: str, at: str) -> dict[str, Any]:
    """The one-line form of an event (a ``BehaviourEvent.model_dump()`` or a legacy log ``e``) at a transition."""
    lat, lon = e.get("lat"), e.get("lon")
    return {"id": e.get("id"), "kind": e.get("kind"), "state": state, "mmsi": e.get("mmsi"), "imo": e.get("imo") or "", "name": e.get("name") or "",
            "ship_class": e.get("ship_class") or "", "at": at, "lat": round(lat, 3) if isinstance(lat, (int, float)) else None,
            "lon": round(lon, 3) if isinstance(lon, (int, float)) else None, "area": e.get("area") or "",
            "confidence": round(float(e.get("confidence") or 0), 2)}


def normalize(obj: dict[str, Any]) -> tuple[dict[str, Any], dict[str, Any] | None, bool] | None:
    """A log line of either generation -> ``(compact line, the full event if the line had one, born_closed)``; ``None`` for what is not a
    transition (legacy "ongoing", torn lines). ``born_closed``: a legacy "open" whose event was already over when first seen (identity)."""
    if "e" in obj:                                            # legacy: {"event": ..., "at": ..., "e": {full event}}
        state, e = str(obj.get("event", "")), obj.get("e") or {}
        if state not in STATES or not e:
            return None
        return compact(e, state, str(obj.get("at", ""))), e, state == "open" and e.get("state", "ongoing") != "ongoing"
    if obj.get("state") in STATES and obj.get("id"):
        return obj, None, False
    return None


class Ledger:
    """Which transitions of which ids are already on record, and when each vessel + kind last opened (see the module doc)."""

    def __init__(self, ids: dict[str, list] | None = None, vk: dict[str, float] | None = None) -> None:
        self.ids: dict[str, list] = ids or {}            # id -> [letters among o/e/u/x, last touched epoch]
        self.vk: dict[str, float] = vk or {}
        self.dirty = False

    @classmethod
    def load(cls, path: Path) -> "Ledger":
        try:
            doc = json.loads(path.read_text(encoding="utf-8"))
            return cls(doc.get("ids") or {}, doc.get("vk") or {})
        except (OSError, ValueError, AttributeError):
            return cls()

    def save(self, path: Path, now: float) -> None:
        if not self.dirty:
            return
        horizon = now - flags.RETAIN_DAYS * 86400
        self.ids = {k: v for k, v in self.ids.items() if v[1] >= horizon}
        longest = max(flags.LOG_COOLDOWN_S.values())
        self.vk = {k: t for k, t in self.vk.items() if t >= now - longest}
        path.parent.mkdir(parents=True, exist_ok=True)
        tmp = path.with_suffix(".tmp")
        tmp.write_text(json.dumps({"ids": self.ids, "vk": self.vk}, separators=(",", ":")), encoding="utf-8")
        os.replace(tmp, path)
        self.dirty = False

    def closed(self, eid: str) -> bool:
        """True when this id's end is already on record (so a detector finding it again is not news)."""
        return any(c in self.ids.get(eid, ("", 0))[0] for c in "eu")

    def mark(self, eid: str, letter: str, now: float) -> None:
        rec = self.ids.setdefault(eid, ["", now])
        if letter not in rec[0]:
            rec[0] += letter
        rec[1] = now
        self.dirty = True

    def admit(self, eid: str, kind: str, mmsi: Any, state: str, now: float, born_closed: bool = False) -> bool:
        """Should this transition be written? Records it when yes."""
        have = self.ids.get(eid, ("", 0))[0]
        if state == "open":
            if "o" in have or "x" in have:
                return False
            key, cooldown = f"{mmsi}:{kind}", flags.LOG_COOLDOWN_S.get(kind, 0)
            if cooldown and now - self.vk.get(key, -1e18) < cooldown:
                self.mark(eid, "x", now)                  # the same vessel's same behaviour: kept in the picture, not written again
                return False
            self.vk[key] = now
            self.mark(eid, "o", now)
            if born_closed:
                self.mark(eid, "e", now)
            return True
        if "x" in have or any(c in have for c in "eu"):
            return False
        self.mark(eid, _TERMINAL[state], now)
        return True


def append(root: Path, line: dict[str, Any]) -> None:
    path = root / LOG
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8", newline="\n") as fh:
        fh.write(json.dumps(line, ensure_ascii=False, separators=(",", ":")) + "\n")
