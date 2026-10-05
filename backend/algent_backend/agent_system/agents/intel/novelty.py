"""
Novelty — what is NEW in a theater since the desk last wrote about it. Counted, never judged.

The desk's focus follows the world only if "something new happened" is a measurement, not a feeling.
This module counts, per theater, the items dated after ``since`` (the date of its last daily section, or
the start of the window for a theater never covered):

* ``headlines``   — member headlines by source class (radar / wikipedia / library): a library document
                    matched into a theater by the clustering is a new library document for it;
* ``statements``  — statements on record that ``sensing`` ties to the theater (every qualifying one, not
                    just the few shown to a writer);
* ``instruments`` — matched series that are unusual NOW and were not unusual as of ``since`` (a series that
                    has been off its range for a month is not news each day; the day it left its range is);
* ``newest``      — the date of the newest of all of those; ``total`` — the count.

Mechanics only (harness-ethos): which of the new items MATTERS is the section writer's judgment, and a
theater with items but no change in substance gets a short section that says so (daily doctrine).
"""

from __future__ import annotations

from datetime import date, timedelta
from typing import Any

from algent_backend.instruments import evidence

from . import sensing
from .base import CLASSES
from .contracts import Theater


def _flagged(tags: list[str], day: date | None) -> dict[str, str]:
    """series_id -> latest reading date, for the unusual series among those matching ``tags`` as of ``day``."""
    try:
        return {r["series_id"]: r["latest"]["period"] for r in evidence.moves_board(tags, as_of=day) if r["unusual"]}
    except Exception:  # noqa: BLE001 - a broken store means no instrument novelty, not a failed board
        return {}


def measure(theater: Theater, *, since: str, as_of: date, ev: sensing.Evidence | None = None) -> dict[str, Any]:
    """The novelty block for one theater (see module docstring). ``ev`` is its sensing evidence (None: headlines only)."""
    headlines = {c: 0 for c in CLASSES}
    newest: list[str] = []
    for m in theater.members:
        day = m.edition[:10]
        if day > since:
            headlines[m.kind] = headlines.get(m.kind, 0) + 1
            newest.append(day)
    statements = [d for d in (ev.statement_dates if ev else []) if d > since]
    instruments: dict[str, str] = {}
    if ev and ev.instrument_rows:
        ids = {r["series_id"] for r in ev.instrument_rows}
        before = _flagged(ev.tags, date.fromisoformat(since)) if since else {}
        instruments = {sid: d for sid, d in _flagged(ev.tags, as_of).items()
                       if sid in ids and sid not in before and d > since}
    newest += statements + list(instruments.values())
    total = sum(headlines.values()) + len(statements) + len(instruments)
    return {"since": since, "headlines": headlines, "statements": len(statements), "instruments": len(instruments),
            "total": total, "newest": max(newest, default="")}


def since_for(last_section: str, *, as_of: date, days: int) -> str:
    """The date novelty counts after: the last section's date, else the day before the window opens."""
    return last_section or (as_of - timedelta(days=days)).isoformat()
