"""
EIA weekly stock reports: the Weekly Petroleum Status Report (normally Wednesday) and the Natural Gas Storage Report (normally
Thursday). Both run every week, so the dates are generated from that rule and the holiday exceptions EIA lists on its schedule pages
replace the standard day of their week. Graded ``announced`` (EIA's published pattern plus its own exceptions), importance routine.
"""

from __future__ import annotations

import re
from datetime import date, timedelta

from algent_backend import polite_http

from ..contracts import CalendarItem, make
from . import HORIZON_DAYS, iso, month_no, upcoming

PETROLEUM_URL = "https://www.eia.gov/petroleum/supply/weekly/schedule.php"
GAS_URL = "https://ir.eia.gov/ngs/schedule.html"
_DATE = r"([A-Z][a-z]+)\s+(\d{1,2}),\s+(\d{4})"
_PETROLEUM_ROW = re.compile(rf'<th scope="row">[^<]*</th>\s*<td[^>]*>\s*{_DATE}\s*</td>')
_GAS_ROW = re.compile(rf"<tr[^>]*>\s*<td>\s*{_DATE}")


def _days(rx: re.Pattern[str], html: str) -> list[date]:
    out = []
    for m in rx.finditer(html):
        mo = month_no(m.group(1))
        d = iso(int(m.group(3)), mo, int(m.group(2))) if mo else ""
        if d:
            out.append(date.fromisoformat(d))
    return out


def parse_exceptions_petroleum(html: str) -> list[date]:
    """The new release dates of holiday weeks (second column of the schedule table)."""
    return _days(_PETROLEUM_ROW, html)


def parse_exceptions_gas(html: str) -> list[date]:
    return _days(_GAS_ROW, html)


def weekly(today: date, weekday: int, exceptions: list[date], days: int = HORIZON_DAYS) -> list[date]:
    """Every ``weekday`` (0 Monday) from today to ``today + days``; an exception date replaces the standard day of its own Monday-first week."""
    by_week = {e - timedelta(days=e.weekday()): e for e in exceptions}
    first = today - timedelta(days=today.weekday())
    out = []
    for k in range(days // 7 + 2):
        monday = first + timedelta(days=7 * k)
        d = by_week.get(monday, monday + timedelta(days=weekday))
        if today <= d <= today + timedelta(days=days):
            out.append(d)
    return out


def make_items(dates: list[date], source: str, title: str, url: str) -> list[CalendarItem]:
    return [make("commodity_report", source, d.isoformat(), title, url, countries=["US"], grade="announced", confidence="high") for d in dates]


def fetch_petroleum(today: date) -> list[CalendarItem]:
    exc = parse_exceptions_petroleum(polite_http.get(PETROLEUM_URL))
    return make_items(weekly(today, 2, exc), "eia_petroleum", "EIA weekly US crude and fuel stocks", PETROLEUM_URL)


def fetch_gas(today: date) -> list[CalendarItem]:
    exc = parse_exceptions_gas(polite_http.get(GAS_URL))
    return make_items(weekly(today, 3, exc), "eia_gas", "EIA weekly US natural gas storage", GAS_URL)


__all__ = ["fetch_petroleum", "fetch_gas", "upcoming"]
