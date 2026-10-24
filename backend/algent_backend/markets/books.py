"""
The two agent books. Both run the same trader (``trader.py``) on the same guards, ledger format and arithmetic (``book.py``); they differ only in
WHICH markets they look at, HOW OFTEN they decide and how much they may spend, so their results can be compared by horizon:

* ``daily``: the original book, every market with a recent blind forecast, decided once a UTC day (``flags.TRADE_*``). Equity series ``trader``.
* ``fast``: only markets that settle within ``flags.FAST_HORIZON_DAYS``, decided every few hours (``flags.FAST_*``), so wins and losses arrive
  quickly. Its own $10k, its own spend cap, equity series ``fast``.

A line's ``book`` field says which ledger it belongs to; lines written before the fast book existed are ``daily``.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime, timedelta

from . import flags, store
from .contracts import Market


@dataclass(frozen=True)
class BookSpec:
    name: str                                  # the ``book`` tag on forecasts and decisions
    equity: str                                # the EquityPoint.book series
    in_scope: Callable[[Market, datetime], bool]
    max_usd_day: Callable[[], float]
    max_usd_run: Callable[[], float]
    max_markets: Callable[[], int]
    call_cap_usd: Callable[[], float]
    forecast_max_age: Callable[[], timedelta]
    enabled: Callable[[], bool]


def _fast_scope(m: Market, now: datetime) -> bool:
    end = store.parse_iso(m.end_date)
    return end is not None and timedelta(hours=flags.FAST_MIN_HOURS_LEFT) <= end - now <= timedelta(days=flags.FAST_HORIZON_DAYS)


DAILY = BookSpec("daily", "trader", lambda m, now: True, lambda: flags.TRADE_MAX_USD_PER_DAY, lambda: flags.TRADE_MAX_USD_PER_DAY,
                 lambda: flags.TRADE_MAX_MARKETS_PER_DAY, lambda: flags.TRADE_CALL_CAP_USD, lambda: timedelta(days=flags.TRADE_FORECAST_MAX_AGE_DAYS),
                 lambda: flags.TRADE_ENABLED)
FAST = BookSpec("fast", "fast", _fast_scope, lambda: flags.FAST_MAX_USD_PER_DAY, lambda: flags.FAST_MAX_USD_PER_RUN,
                lambda: flags.FAST_MAX_MARKETS_PER_RUN, lambda: min(flags.TRADE_CALL_CAP_USD, flags.FAST_MAX_USD_PER_RUN),
                lambda: timedelta(hours=flags.FAST_FORECAST_MAX_AGE_H), lambda: flags.FAST_ENABLED and flags.TRADE_ENABLED)

BOOKS = {"daily": DAILY, "fast": FAST}


def get(name: str) -> BookSpec:
    return BOOKS[name]


def recent_ids(ds: list, now: datetime, spec: BookSpec) -> set[str]:
    """Markets this book already decided on recently enough not to ask again: today (daily), or within ``FAST_RECHECK_H`` hours (fast)."""
    if spec.name == "fast":
        floor = now - timedelta(hours=flags.FAST_RECHECK_H)
        return {d.market_id for d in ds if d.action != "settle" and (store.parse_iso(d.at) or now) >= floor}
    day = now.date().isoformat()
    return {d.market_id for d in ds if d.action != "settle" and d.day == day}


def spend_today(ds: list, forecasts: list, now: datetime, spec: BookSpec) -> float:
    """What this book has spent today (UTC): its decisions, plus (fast only) the forecasts it ordered; the daily forecast pass has its own cap."""
    day = now.date().isoformat()
    spent = sum(d.usd for d in ds if d.day == day and d.action != "settle")
    if spec.name == "fast":
        spent += sum(f.usd for f in forecasts if f.book == "fast" and f.made_at.startswith(day))
    return round(spent, 6)
