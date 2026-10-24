"""
Collector — ask each schedule source for its upcoming items and sync them into the store.

One source at a time, each isolated (a page down, blocked or re-laid-out is recorded and never stops the others). A source that
returns nothing is treated as a failure, not as "everything was cancelled": it must not withdraw its items. The exception is
``MAY_BE_EMPTY``: sources whose honest answer is sometimes "nothing" (no hearing scheduled, no market open); for those an empty
list is a result and withdraws what is no longer listed.

Cadence classes (jobs in ops/products/registry.py): ``schedules`` runs daily (official calendars change rarely); ``fast`` every
six hours (launch dates slip, earnings dates get confirmed, markets open and close, watches are added by the desk).
"""

from __future__ import annotations

from collections.abc import Callable
from datetime import date
from typing import Any

from . import store
from .contracts import CalendarItem
from .sources import (ai_act, bea, bls_jobs, boj, central_banks, earnings, eia, elections, icj, launches, norges, own, pboc_lpr, rba, summits, tech_events,
                      un_opec, unsc_presidency, wasde)

Fetcher = Callable[[date], list[CalendarItem]]

FETCHERS: dict[str, Fetcher] = {
    # central banks
    "fed": central_banks.fetch_fed, "ecb": central_banks.fetch_ecb, "boe": central_banks.fetch_boe, "boj": boj.fetch, "rba": rba.fetch,
    "norges": norges.fetch, "pboc": pboc_lpr.fetch,
    # economic releases, commodities and energy
    "bea": bea.fetch, "bls_jobs": bls_jobs.fetch, "wasde": wasde.fetch, "eia_petroleum": eia.fetch_petroleum, "eia_gas": eia.fetch_gas, "opec": un_opec.fetch_opec,
    # elections, diplomacy and law
    "elections": elections.fetch, "unsc": un_opec.fetch_unsc, "unsc_presidency": unsc_presidency.fetch, "icj": icj.fetch, "summits": summits.fetch,
    # AI and tech
    "ai_act": ai_act.fetch, "gtc": tech_events.fetch_gtc, "earnings": earnings.fetch,
    # space
    "launches": launches.fetch,
    # our own system
    "markets": own.fetch_markets, "watches": own.fetch_watches,
}
#: cadence class -> sources. Every source is in exactly one (tests/test_lookahead.py).
GROUPS: dict[str, tuple[str, ...]] = {
    "fast": ("earnings", "launches", "markets", "watches"),
    "schedules": tuple(s for s in FETCHERS if s not in ("earnings", "launches", "markets", "watches")),
}
MAY_BE_EMPTY = frozenset({"icj", "markets", "watches"})


def names(group: str | None = None) -> list[str]:
    return list(GROUPS[group]) if group else list(FETCHERS)


def refresh(sources: list[str] | None = None, *, today: date | None = None, fetchers: dict[str, Fetcher] | None = None,
            group: str | None = None) -> dict[str, Any]:
    today = today or date.today()
    fetchers = fetchers or FETCHERS
    rows = []
    for src in sources or ([s for s in GROUPS[group] if s in fetchers] if group else list(fetchers)):
        row: dict[str, Any] = {"source": src}
        try:
            items = fetchers[src](today)
            if not items and src not in MAY_BE_EMPTY:
                raise ValueError("no upcoming items parsed (layout change, or nothing scheduled)")
            res = store.sync(src, items, today)
            row.update(status="ok", items=len(items), **res)
            store.save_status(src, last_ok=store.now_iso(), last_error="", items=len(items))
        except Exception as exc:  # noqa: BLE001 - one broken page must not stop the others
            row.update(status="error", error=f"{type(exc).__name__}: {str(exc)[:200]}")
            store.save_status(src, last_error=row["error"], last_error_at=store.now_iso())
        rows.append(row)
    return {"as_of": today.isoformat(), "sources": rows}
