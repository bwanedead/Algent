"""
Collector — read each source, drop what is already on file, join assets, append.

One source at a time, each isolated: a source being down, unparseable or (keyed) unconfigured is recorded in the report and the status file
and never stops the others. GDELT is read file by file from a cursor so a late timer catches up and a rerun repeats nothing; a keyed source with
no key is reported as ``needs-key`` (not an error: the doctor does not warn about it).
"""

from __future__ import annotations

from collections.abc import Callable
from datetime import date, datetime, timedelta, UTC
from typing import Any

from algent_backend.polite_http import SourceError, SourceUnavailable, get, post_form

from . import assets, flags, store
from .contracts import SOURCES, ConflictEvent, neighbour_ids
from .sources import NeedsKey, acled, gdelt, reliefweb, ucdp


def novel(events: list[ConflictEvent]) -> list[ConflictEvent]:
    """Events not already on file or earlier in the batch. An event is the same one if it has the same key within DEDUPE_DAYS of its date."""
    days: set[str] = set()
    for e in events:
        d0 = date.fromisoformat(e.date)
        days |= {(d0 + timedelta(days=k)).isoformat() for k in range(-flags.DEDUPE_DAYS, flags.DEDUPE_DAYS + 1)}
    seen = store.known_ids(days & set(store.shard_days()))
    out = []
    for e in events:
        near = neighbour_ids(e.source, e.key, e.date, flags.DEDUPE_DAYS) if e.key else [e.id]
        if any(i in seen for i in near):
            continue
        seen.add(e.id)
        out.append(e)
    return out


def _gdelt(row: dict[str, Any], fetch_file: Callable[[str], list[ConflictEvent]], latest: Callable[[], str]) -> list[ConflictEvent]:
    last = latest()
    cursor = str(store.load_cursor().get("gdelt", ""))
    todo = gdelt.stamps_after(cursor, last)
    found: list[ConflictEvent] = []
    files = 0
    for stamp in todo:
        try:
            evs = fetch_file(stamp)
        except SourceError:
            if stamp == last:
                raise                                       # the newest file not being there yet is a failure: try again next run
            store.save_cursor(gdelt=stamp)                  # an older file GDELT never produced: do not wait for it forever
            continue
        fresh = novel(evs)
        assets.attach(fresh)
        found += store.append(fresh)
        store.save_cursor(gdelt=stamp)
        files += 1
    row.update(files=files, behind=max(0, len(todo) - files))
    return found


def collect(sources: list[str] | None = None, *, today: date | None = None, fetchers: dict[str, Callable[..., Any]] | None = None) -> dict[str, Any]:
    """Run the named sources (default all). ``fetchers`` replaces the network seams in tests: gdelt_file, gdelt_latest, reliefweb, acled, ucdp."""
    today = today or date.today()
    fx = fetchers or {}
    observed = datetime.now(UTC).isoformat(timespec="seconds")
    rows, found = [], []
    for src in sources or list(SOURCES):
        row: dict[str, Any] = {"source": src}
        try:
            if src == "gdelt":
                new = _gdelt(row, fx.get("gdelt_file", gdelt.fetch_file), fx.get("gdelt_latest", gdelt.latest_stamp))
            else:
                run = fx.get(src) or {"reliefweb": lambda: reliefweb.fetch(observed, get=get, today=today),
                                      "acled": lambda: acled.fetch(observed, get=get, post=post_form, today=today),
                                      "ucdp": lambda: ucdp.fetch(observed, get=get, today=today)}[src]
                evs = run()
                fresh = novel(evs)
                assets.attach(fresh)
                new = store.append(fresh)
                row["seen"] = len(evs)
            found += new
            row.update(status="ok", new=len(new))
            store.save_status(src, last_ok=store.now_iso(), last_error="", last_new=len(new))
        except NeedsKey as exc:
            row.update(status="needs-key", note=str(exc)[:240])
            store.save_status(src, needs_key=str(exc)[:240])
        except (SourceUnavailable, SourceError, ValueError, OSError) as exc:
            row.update(status="error", error=f"{type(exc).__name__}: {str(exc)[:200]}")
            store.save_status(src, last_error=row["error"], last_error_at=store.now_iso())
        except Exception as exc:  # noqa: BLE001 - a parser surprise must not take the other sources down
            row.update(status="error", error=f"{type(exc).__name__}: {str(exc)[:200]}")
            store.save_status(src, last_error=row["error"], last_error_at=store.now_iso())
        rows.append(row)
    return {"as_of": today.isoformat(), "sources": rows, "new": len(found)}
