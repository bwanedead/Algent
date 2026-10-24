"""
US Employment Situation (the monthly jobs report). bls.gov answers scripted clients with 403, so its schedule cannot be fetched; the date
follows a published rule instead: the report comes out on the third Friday after the end of the reference week, the Sunday-to-Saturday
week that contains the 12th. Generated from the rule, so graded ``estimated`` (a shutdown or a holiday can move it; the BLS release
calendar is linked as the place to confirm). CPI has no such rule and is left out until a fetchable source exists.
"""

from __future__ import annotations

from datetime import date, timedelta

from ..contracts import CalendarItem, make
from . import HORIZON_DAYS

URL = "https://www.bls.gov/schedule/news_release/empsit.htm"


def release_day(year: int, month: int) -> date:
    twelfth = date(year, month, 12)
    week_end = twelfth + timedelta(days=(5 - twelfth.weekday()) % 7)               # the Saturday that ends the week holding the 12th
    return week_end + timedelta(days=(4 - week_end.weekday()) % 7 + 14)             # first Friday after it, plus two more weeks


def fetch(today: date) -> list[CalendarItem]:
    out, y, m = [], today.year, today.month
    for _ in range(HORIZON_DAYS // 28 + 2):
        d = release_day(y, m)
        if today <= d <= today + timedelta(days=HORIZON_DAYS):
            out.append(make("data_release", "bls_jobs", d.isoformat(), "US jobs report (BLS), expected date", URL, countries=["US"], grade="estimated"))
        y, m = (y + 1, 1) if m == 12 else (y, m + 1)
    return out
