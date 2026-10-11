"""
Freshness — is a series' latest reading as new as its SOURCE can make it?

A reading's age means nothing without the source's rhythm: IMF PortWatch publishes weekly and a week behind, so
a Hormuz count dated 7 days ago is as fresh as that feed gets, while a Treasury yield that old is broken. Each
catalog series declares ``cadence`` (how often it releases) and ``lag_days`` (period end -> publication);
a reading is ``current`` until the next release is overdue, and ``overdue`` only then (a real fetch problem).

Pure and deterministic: no I/O, no model. ``CADENCE_DAYS`` is the gap between releases; a daily feed is 3 so a
weekend plus a market holiday is not an alarm.
"""

from __future__ import annotations

import calendar
from datetime import date

from .contracts import Series, period_date

CADENCE_DAYS = {"daily": 3, "weekly": 7, "monthly": 31, "annual": 366}
STEP_LABEL = {"daily": "prior day", "weekly": "prior week", "monthly": "prior month", "annual": "prior year"}


def period_end(period: str) -> date:
    """Last day a period covers: the date itself, or the last day of a ``YYYY-MM`` month."""
    d = period_date(period)
    return date(d.year, d.month, calendar.monthrange(d.year, d.month)[1]) if len(period) == 7 else d


def _short(d: date) -> str:
    return f"{d.day} {d.strftime('%b')}"


def assess(series: Series, latest_period: str, today: date) -> dict:
    """{cadence, lag_days, status, days_overdue, note} for ``series`` whose newest period is ``latest_period``."""
    end = period_end(latest_period)
    late = max(0, (today - end).days - (CADENCE_DAYS[series.cadence] + series.lag_days))
    what = {"weekly": f"latest week to {_short(end)}", "monthly": f"latest month: {end.strftime('%b %Y')}",
            "annual": f"latest year: {end.year}"}.get(series.cadence, f"latest {_short(end)}")
    note = f"{series.cadence} data · {what}" + (f" · overdue by {late} d" if late else "")
    return {"cadence": series.cadence, "lag_days": series.lag_days, "status": "overdue" if late else "current",
            "days_overdue": late, "note": note}


def step_key(series: Series) -> str:
    """The change horizon that is this series' natural step: a weekly-released feed of daily counts compares
    against a week earlier ('7d'), never against the previous day; everything else against the previous reading."""
    return "7d" if series.cadence == "weekly" and series.frequency == "daily" else "prev"
