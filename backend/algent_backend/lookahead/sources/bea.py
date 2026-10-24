"""
US Bureau of Economic Analysis release schedule (bea.gov/news/schedule): only the two top-tier releases, GDP (advance, second, third
estimates) and Personal Income and Outlays (the PCE inflation release). The page lists "Month day" per release under a "Year" heading.
Official page.
"""

from __future__ import annotations

import re
from datetime import date

from algent_backend import polite_http

from ..contracts import CalendarItem, make
from . import iso, month_no, plain, upcoming

URL = "https://www.bea.gov/news/schedule"
_TOKEN = re.compile(r'Year\s+(\d{4})|class="release-date">\s*([A-Za-z]+)\s+(\d{1,2})\s*</div>|class="release-title[^"]*"[^>]*>(.*?)</td>', re.S)


def _title(raw: str) -> str:
    t = plain(raw)
    if t.startswith("GDP ("):
        m = re.match(r"GDP \(([A-Za-z]+) Estimate\)", t)
        return f"US GDP, {m.group(1).lower()} estimate" if m else "US GDP"
    if t.startswith("Personal Income and Outlays"):
        return "US personal income and spending (PCE inflation)"
    return ""


def parse(html: str) -> list[CalendarItem]:
    out, year, pending = [], 0, ""
    for m in _TOKEN.finditer(html):
        if m.group(1):
            year = int(m.group(1))
        elif m.group(2):
            mo = month_no(m.group(2))
            pending = iso(year, mo, int(m.group(3))) if year and mo else ""
        elif pending:
            title = _title(m.group(4))
            if title:
                out.append(make("data_release", "bea", pending, title, URL, countries=["US"]))
            pending = ""
    return out


def fetch(today: date) -> list[CalendarItem]:
    return upcoming(parse(polite_http.get(URL)), today)
