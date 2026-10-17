"""
Collector — fetch each list, diff it against its last snapshot, append the events, keep the new snapshot.

One source at a time, each isolated: a list being down or unparseable is recorded in the report and the status file and never
stops the others. A refused snapshot (see ``diff``) leaves the previous one in place. Vessel designations are linked into the
geoledger afterwards.
"""

from __future__ import annotations

import tempfile
from collections.abc import Callable
from datetime import date
from pathlib import Path
from typing import Any

from algent_backend.polite_http import SourceError, SourceUnavailable

from . import store, vessels
from .contracts import SOURCES, Entry
from .diff import diff
from .sources import eu, ofac, uk

#: source id -> fetch(workdir) -> entries
FETCHERS: dict[str, Callable[[Path], dict[str, Entry]]] = {"ofac": ofac.fetch, "uk": uk.fetch, "eu": eu.fetch}


def collect(sources: list[str] | None = None, *, today: date | None = None,
            fetchers: dict[str, Callable[[Path], dict[str, Entry]]] | None = None, link_vessels: bool = True) -> dict[str, Any]:
    today = today or date.today()
    fetchers = fetchers or FETCHERS
    rows, found = [], []
    with tempfile.TemporaryDirectory(prefix="sanctions_") as tmp:
        for src in sources or list(SOURCES):
            row: dict[str, Any] = {"source": src}
            try:
                entries = fetchers[src](Path(tmp))
                if not entries:
                    raise ValueError("the list parsed to nothing")
                old = store.load_snapshot(src)
                events = diff(src, old, entries, today)
                row.update(status="ok", entries=len(entries), baseline=old is None, events=len(events),
                           new=store.append_events(events))
                store.save_snapshot(src, entries)
                store.save_status(src, last_ok=store.now_iso(), last_error="", entries=len(entries), last_events=len(events))
                found += events
            except (SourceUnavailable, SourceError, ValueError, OSError) as exc:
                row.update(status="error", error=f"{type(exc).__name__}: {str(exc)[:200]}")
                store.save_status(src, last_error=f"{type(exc).__name__}: {str(exc)[:200]}", last_error_at=store.now_iso())
            except Exception as exc:  # noqa: BLE001 - a parser surprise must not take the other lists down
                row.update(status="error", error=f"{type(exc).__name__}: {str(exc)[:200]}")
                store.save_status(src, last_error=row["error"], last_error_at=store.now_iso())
            rows.append(row)
    report: dict[str, Any] = {"as_of": today.isoformat(), "sources": rows}
    if link_vessels and found:
        report["vessels"] = vessels.link(found)
    return report
