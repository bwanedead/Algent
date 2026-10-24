"""
AI and tech conferences announced on their own sites. Today: NVIDIA GTC (the nvidia.com/gtc page states "GTC San Jose 2027 is coming
March 15–18"). The other flagship events (Google I/O, Apple WWDC, Microsoft Build, OpenAI DevDay, NeurIPS) are spring, summer or
autumn fixtures whose next dates are published late or behind scripts or bot walls; they join here, one parser each, when a
machine-readable announcement exists (docs/architecture/sanctions-calendar.md lists what was tried).
"""

from __future__ import annotations

import re
from datetime import date

from algent_backend import polite_http

from ..contracts import CalendarItem, make
from . import iso, month_no, upcoming

GTC_URL = "https://www.nvidia.com/gtc/"
_GTC = re.compile(r"GTC\s+([A-Za-z ]{0,20}?)(\d{4}) is coming\s+([A-Za-z]+)\s+(\d{1,2})\s*[–-]\s*(\d{1,2})")


def parse_gtc(html: str) -> list[CalendarItem]:
    m = _GTC.search(html)
    if not m:
        return []
    mo = month_no(m.group(3))
    first, last = (iso(int(m.group(2)), mo, int(m.group(4))), iso(int(m.group(2)), mo, int(m.group(5)))) if mo else ("", "")
    place = m.group(1).strip()
    return [make("conference", "gtc", first, f"NVIDIA GTC {m.group(2)}{', ' + place if place else ''}", GTC_URL, end_date=last, countries=["US"])] if first else []


def fetch_gtc(today: date) -> list[CalendarItem]:
    return upcoming(parse_gtc(polite_http.get(GTC_URL)), today)
