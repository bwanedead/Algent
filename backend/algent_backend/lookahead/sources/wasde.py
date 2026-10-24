"""
USDA World Agricultural Supply and Demand Estimates (WASDE): the Office of the Chief Economist publishes a sentence per year,
"In 2026 the WASDE report will be released on Jan. 12, Feb. 10, ...". Official page.
"""

from __future__ import annotations

import re
from datetime import date

from algent_backend import polite_http

from ..contracts import CalendarItem, make
from . import iso, month_no, plain, upcoming

URL = "https://www.usda.gov/about-usda/general-information/staff-offices/office-chief-economist/commodity-markets/wasde-report"
_SENT = re.compile(r"In (\d{4}) the WASDE report will be released on ([^<]*?)\.\s*(?:<|$)")
_DAY = re.compile(r"([A-Za-z]{3,9})\.?\s+(\d{1,2})")


def parse(html: str) -> list[CalendarItem]:
    out = []
    for m in _SENT.finditer(html.replace("&nbsp;", " ")):
        for d in _DAY.finditer(plain(m.group(2))):
            mo = month_no(d.group(1))
            day = iso(int(m.group(1)), mo, int(d.group(2))) if mo else ""
            if day:
                out.append(make("commodity_report", "wasde", day, "USDA WASDE crop supply and demand report", URL, countries=["US"]))
    return out


def fetch(today: date) -> list[CalendarItem]:
    return upcoming(parse(polite_http.get(URL)), today)
