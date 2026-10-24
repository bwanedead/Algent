"""
Big-tech earnings dates. The companies' investor-relations pages are script-rendered or bot-walled (NVIDIA, TSMC and ASML answer 403),
so the dates come from Nasdaq's public earnings calendar JSON (api.nasdaq.com, no key), one request per weekday for the weeks ahead,
filtered to a fixed list of companies. A date more than ``CONFIRMED_DAYS`` out is a projection, so it is graded ``estimated``.
"""

from __future__ import annotations

from datetime import date, timedelta

from algent_backend import polite_http

from ..contracts import CalendarItem, make
from . import upcoming

API = "https://api.nasdaq.com/api/calendar/earnings"
PAGE = "https://www.nasdaq.com/market-activity/earnings"
#: symbol -> (name, ISO2 of the listing company's home). GOOG/GOOGL are one company (one item per day after the merge).
COMPANIES = {"NVDA": ("NVIDIA", "US"), "MSFT": ("Microsoft", "US"), "GOOGL": ("Alphabet", "US"), "GOOG": ("Alphabet", "US"), "META": ("Meta", "US"),
             "AMZN": ("Amazon", "US"), "AAPL": ("Apple", "US"), "TSM": ("TSMC", "TW"), "ASML": ("ASML", "NL")}
WEEKDAYS_AHEAD = 40         # eight weeks: companies confirm a date about three to four weeks out, so more only fetches projections
CONFIRMED_DAYS = 30


def parse(day: str, payload: dict, today: date) -> list[CalendarItem]:
    rows = ((payload or {}).get("data") or {}).get("rows") or []
    near = (date.fromisoformat(day) - today).days <= CONFIRMED_DAYS
    out = []
    for r in rows:
        sym = str(r.get("symbol") or "").upper()
        if sym in COMPANIES:
            name, iso2 = COMPANIES[sym]
            out.append(make("earnings", "earnings", day, f"{name} quarterly earnings", PAGE, countries=[iso2], grade="announced" if near else "estimated"))
    return list({i.id: i for i in out}.values())


def fetch(today: date) -> list[CalendarItem]:
    out, d, n = [], today, 0
    while n < WEEKDAYS_AHEAD:
        if d.weekday() < 5:
            n += 1
            payload = polite_http.get(API, params={"date": d.isoformat()}, headers={"Accept": "application/json"})
            import json

            out += parse(d.isoformat(), json.loads(payload), today)
        d += timedelta(days=1)
    return upcoming(out, today)
