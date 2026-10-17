"""
Calendar store on disk — append-only revisions of items.

    <root>/items.jsonl   one CalendarItem REVISION per line (a changed or withdrawn item is a new line; the last line of an id wins)
    <root>/status.json   per source: last good fetch, last error, items found

Root: ``ALGENT_CALENDAR_STORE`` or ``calendar_store``. ``sync`` is how a source reports: it writes the new and changed items,
and marks an upcoming item the source no longer lists as inactive (a date moved or was cancelled) — history stays on file.
"""

from __future__ import annotations

import json
import os
from datetime import UTC, date, datetime
from pathlib import Path

from .contracts import CalendarItem

_ENV = "ALGENT_CALENDAR_STORE"


def root() -> Path:
    return Path(os.environ.get(_ENV) or "calendar_store")


def now_iso() -> str:
    return datetime.now(UTC).isoformat(timespec="seconds")


def revisions() -> list[CalendarItem]:
    try:
        lines = (root() / "items.jsonl").read_text(encoding="utf-8").splitlines()
    except OSError:
        return []
    out = []
    for line in lines:
        try:
            out.append(CalendarItem.model_validate_json(line))
        except ValueError:
            continue                                # a torn line must not hide the rest
    return out


def current() -> dict[str, CalendarItem]:
    """The latest revision of every item."""
    return {i.id: i for i in revisions()}


def _same(a: CalendarItem, b: CalendarItem) -> bool:
    skip = {"first_seen", "updated_at"}
    return a.model_dump(exclude=skip) == b.model_dump(exclude=skip)


def _append(items: list[CalendarItem]) -> None:
    if not items:
        return
    path = root() / "items.jsonl"
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8", newline="\n") as fh:
        fh.write("\n".join(i.model_dump_json() for i in items) + "\n")


def sync(source: str, items: list[CalendarItem], today: date, *, withdraw: bool = True) -> dict[str, int]:
    """Record ``source``'s current upcoming items. With ``withdraw`` (every official-schedule source), an upcoming item of this
    source that is no longer listed becomes inactive. Without it (the corpus extractor, which only ever adds) items accumulate."""
    have = current()
    now, rows = now_iso(), []
    out = {"new": 0, "changed": 0, "withdrawn": 0, "unchanged": 0}
    listed = {i.id for i in items}
    for it in items:
        old = have.get(it.id)
        if old is not None and it.source == "corpus":
            it = it.model_copy(update={"theaters": sorted(set(old.theaters) | set(it.theaters)),
                                       "via": old.via or it.via, "countries": sorted(set(old.countries) | set(it.countries))})
        it = it.model_copy(update={"first_seen": old.first_seen if old else now, "updated_at": now, "active": True})
        if old is None:
            out["new"] += 1
        elif not _same(old, it):
            out["changed"] += 1
        else:
            out["unchanged"] += 1
            continue
        rows.append(it)
    if withdraw:
        for old in have.values():
            if old.source == source and old.active and old.id not in listed and old.date >= today.isoformat():
                rows.append(old.model_copy(update={"active": False, "updated_at": now}))
                out["withdrawn"] += 1
    _append(rows)
    return out


def upcoming(today: date, days: int, *, active_only: bool = True) -> list[CalendarItem]:
    """Items whose date (or window) touches [today, today + days], soonest first."""
    from datetime import timedelta

    lo, hi = today.isoformat(), (today + timedelta(days=days)).isoformat()
    rows = [i for i in current().values() if (i.active or not active_only) and (i.end_date or i.date) >= lo and i.date <= hi]
    return sorted(rows, key=lambda i: (i.date, i.kind, i.title))


# -- status ---------------------------------------------------------------------------------------
def load_status() -> dict[str, dict]:
    try:
        return json.loads((root() / "status.json").read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}


def save_status(source: str, **fields: object) -> None:
    st = load_status()
    st[source] = {**st.get(source, {}), **fields}
    path = root() / "status.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(st, indent=1, ensure_ascii=False), encoding="utf-8", newline="\n")
