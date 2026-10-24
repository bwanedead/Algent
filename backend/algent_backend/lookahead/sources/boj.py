"""
Bank of Japan monetary policy meetings: the BoJ's own "Past and upcoming meetings" table (one table per year; the first column is the two
meeting days, the decision comes on the second). Official page, cited by link.
"""

from __future__ import annotations

import re
from datetime import date

from algent_backend import polite_http

from ..contracts import CalendarItem, make
from . import iso, month_no, plain, upcoming

URL = "https://www.boj.or.jp/en/mopo/mpmsche_minu/index.htm"
_ROW = re.compile(r"<tr>\s*<td>(.*?)</td>", re.S)
_DAYS = re.compile(r"([A-Z][a-z]{2,4})\.?\s+(\d{1,2})\s*\([A-Za-z.]+\),\s*(\d{1,2})\s*\([A-Za-z.]+\)")


def parse(html: str) -> list[CalendarItem]:
    out = []
    parts = re.split(r"Table\s*:\s*(\d{4})", html)
    for k in range(1, len(parts) - 1, 2):
        year = int(parts[k])
        for row in _ROW.finditer(parts[k + 1]):
            m = _DAYS.search(plain(row.group(1)))
            mo = month_no(m.group(1)) if m else None
            day = iso(year, mo, int(m.group(3))) if m and mo else ""
            if day:
                out.append(make("central_bank", "boj", day, "Bank of Japan rate decision", URL, countries=["JP"]))
    return out


def fetch(today: date) -> list[CalendarItem]:
    return upcoming(parse(polite_http.get(URL)), today)
