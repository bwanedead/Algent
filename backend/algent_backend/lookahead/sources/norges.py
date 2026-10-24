"""
Norges Bank policy-rate decisions from the bank's own calendar page (the events are embedded in the page as JSON records:
``{"title":"Policy rate decision","url":...,"date":"2026-11-05T10:00:00+01:00"}``). Official page.
"""

from __future__ import annotations

import re
from datetime import date

from algent_backend import polite_http

from ..contracts import CalendarItem, make
from . import upcoming

URL = "https://www.norges-bank.no/en/news-events/calendar/"
_REC = re.compile(r'"title":"([^"]*[Pp]olicy rate decision[^"]*)","url":"[^"]*","tag":"[^"]*","date":"(\d{4}-\d{2}-\d{2})')


def parse(html: str) -> list[CalendarItem]:
    return [make("central_bank", "norges", m.group(2), "Norges Bank rate decision", URL, countries=["NO"]) for m in _REC.finditer(html)]


def fetch(today: date) -> list[CalendarItem]:
    return upcoming(parse(polite_http.get(URL)), today)
