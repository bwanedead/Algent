"""
UN Security Council presidency by month, from the Council's own presidency page (a table of "Month Year | Presidency | end of term",
rotating alphabetically). One item on the first day of each month: it names who sets that month's programme of work. The meetings
themselves come from ``un_opec.fetch_unsc``. Official page.
"""

from __future__ import annotations

import re
from datetime import date

from algent_backend import polite_http
from algent_backend.actors import names as cnames

from ..contracts import CalendarItem, make
from . import iso, month_no, plain, upcoming

URL = "https://main.un.org/securitycouncil/en/content/presidency"
_ROW = re.compile(r"<tr><td><p[^>]*>\s*([A-Z][a-z]+)(?:&nbsp;|\s)+(\d{4})\s*</p></td><td><p[^>]*>(.*?)</p></td>", re.S)


def parse(html: str) -> list[CalendarItem]:
    out: dict[str, CalendarItem] = {}
    for m in _ROW.finditer(html):
        mo = month_no(m.group(1))
        day = iso(int(m.group(2)), mo, 1) if mo else ""
        who = plain(m.group(3))
        if day and who:
            iso2 = cnames.iso2(who)
            out[day] = make("security_council", "unsc_presidency", day, f"UN Security Council presidency: {who}", URL, countries=[iso2] if iso2 else [])
    return list(out.values())


def fetch(today: date) -> list[CalendarItem]:
    return upcoming(parse(polite_http.get(URL)), today)
