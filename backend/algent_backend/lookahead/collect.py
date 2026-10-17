"""
Collector — ask each schedule source for its upcoming items and sync them into the store.

One source at a time, each isolated (a page down, blocked or re-laid-out is recorded and never stops the others). A source that
returns nothing is treated as a failure, not as "everything was cancelled": it must not withdraw its items.
"""

from __future__ import annotations

from collections.abc import Callable
from datetime import date
from typing import Any

from . import store
from .contracts import CalendarItem
from .sources import central_banks, elections, un_opec

Fetcher = Callable[[date], list[CalendarItem]]

FETCHERS: dict[str, Fetcher] = {
    "fed": central_banks.fetch_fed, "ecb": central_banks.fetch_ecb, "boe": central_banks.fetch_boe,
    "elections": elections.fetch, "unsc": un_opec.fetch_unsc, "opec": un_opec.fetch_opec,
}


def refresh(sources: list[str] | None = None, *, today: date | None = None, fetchers: dict[str, Fetcher] | None = None) -> dict[str, Any]:
    today = today or date.today()
    fetchers = fetchers or FETCHERS
    rows = []
    for src in sources or list(fetchers):
        row: dict[str, Any] = {"source": src}
        try:
            items = fetchers[src](today)
            if not items:
                raise ValueError("no upcoming items parsed (layout change, or nothing scheduled)")
            res = store.sync(src, items, today)
            row.update(status="ok", items=len(items), **res)
            store.save_status(src, last_ok=store.now_iso(), last_error="", items=len(items))
        except Exception as exc:  # noqa: BLE001 - one broken page must not stop the others
            row.update(status="error", error=f"{type(exc).__name__}: {str(exc)[:200]}")
            store.save_status(src, last_error=row["error"], last_error_at=store.now_iso())
        rows.append(row)
    return {"as_of": today.isoformat(), "sources": rows}
