"""
China's Loan Prime Rate fixing (the PBoC's policy benchmark since 2019): published on the 20th of every month, moved to the next day
when the 20th is a weekend. Generated from that rule, not fetched, so it is graded ``estimated``: public holidays in China can move a
fixing by more days and are not modelled. Linked to the PBoC's English site.
"""

from __future__ import annotations

from datetime import date, timedelta

from ..contracts import CalendarItem, make
from . import HORIZON_DAYS

URL = "https://www.pbc.gov.cn/en/3688006/index.html"


def fixings(today: date, days: int = HORIZON_DAYS) -> list[date]:
    out, y, m = [], today.year, today.month
    for _ in range(days // 28 + 2):
        d = date(y, m, 20)
        while d.weekday() >= 5:
            d += timedelta(days=1)
        if today <= d <= today + timedelta(days=days):
            out.append(d)
        y, m = (y + 1, 1) if m == 12 else (y, m + 1)
    return out


def fetch(today: date) -> list[CalendarItem]:
    return [make("central_bank", "pboc", d.isoformat(), "China Loan Prime Rate fixing", URL, countries=["CN"], grade="estimated") for d in fixings(today)]
