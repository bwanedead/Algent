"""
Reserve Bank of Australia Monetary Policy Board meetings from the RBA's "Board meeting schedules" page (a table per year, one row per
month, first column the Monetary Policy Board's two meeting days; the decision comes on the second). Official page.
"""

from __future__ import annotations

import re
from datetime import date

from algent_backend import polite_http

from ..contracts import CalendarItem, make
from . import plain, span_dates, upcoming

URL = "https://www.rba.gov.au/schedules-events/board-meeting-schedules.html"
_ROW = re.compile(r'<th scope="row">\s*([A-Za-z]+)\s*</th>\s*<td>(.*?)</td>', re.S)


def parse(html: str) -> list[CalendarItem]:
    out = []
    parts = re.split(r"Board meeting schedules\s+(\d{4})", html)
    for k in range(1, len(parts) - 1, 2):
        for row in _ROW.finditer(parts[k + 1]):
            cell = plain(row.group(2))
            if not cell:
                continue
            first, last = span_dates(f"{cell} {parts[k]}")
            day = last or first
            if day:
                out.append(make("central_bank", "rba", day, "Reserve Bank of Australia rate decision", URL, countries=["AU"]))
    return out


def fetch(today: date) -> list[CalendarItem]:
    return upcoming(parse(polite_http.get(URL)), today)
