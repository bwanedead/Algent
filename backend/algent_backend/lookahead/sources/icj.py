"""
International Court of Justice: scheduled public hearings and judgments, from the Court's press-release list. Each press release
carries a title such as "<case> (A v. B) - Public hearings to be held from Monday 7 to Thursday 10 September 2026" or "... - Delivery of
the Judgment on 9 November 2026". Official page; the parties' countries are taken from "A v. B" when both sides are states.
"""

from __future__ import annotations

import re
from datetime import date

from algent_backend import polite_http
from algent_backend.actors import names as cnames

from ..contracts import CalendarItem, make, short
from . import iso, month_no, plain, upcoming

URL = "https://www.icj-cij.org/en/press-releases"
_TITLE = re.compile(r'views-field-title"><p>(.*?)</p>', re.S)
_HEAR = re.compile(r"[Pp]ublic hearings?[^-]*?(?:to be held|will be held|to open)[^-]*?from\s+(?:[A-Za-z]+\s+)?(\d{1,2})(?:\s+([A-Za-z]+))?\s+to\s+(?:[A-Za-z]+\s+)?(\d{1,2})\s+([A-Za-z]+)\s+(\d{4})")
_JUDG = re.compile(r"[Dd]elivery of (?:its |the |an )?(Judgment|Advisory Opinion|Order)[^-]*?on\s+(?:[A-Za-z]+\s+)?(\d{1,2})\s+([A-Za-z]+)\s+(\d{4})")
_PARTIES = re.compile(r"\(([^()]*?)\s+v\.\s+([^()]*?)\)")


def _case(text: str) -> tuple[str, list[str]]:
    m = _PARTIES.search(text)
    if not m:
        return short(text.split(" - ")[0], 6), []
    codes = [c for c in (cnames.iso2(m.group(1).strip()), cnames.iso2(m.group(2).strip())) if c]
    return f"{m.group(1).strip()} v. {m.group(2).strip()}", codes


def parse(html: str) -> list[CalendarItem]:
    out: dict[str, CalendarItem] = {}
    for t in _TITLE.finditer(html):
        text = plain(t.group(1))
        name, codes = _case(text)
        h, j = _HEAR.search(text), _JUDG.search(text)
        if h and not text.lower().startswith("conclusion"):
            y, m2 = int(h.group(5)), month_no(h.group(4))
            m1 = month_no(h.group(2)) if h.group(2) else m2
            first, last = (iso(y, m1, int(h.group(1))), iso(y, m2, int(h.group(3)))) if m1 and m2 else ("", "")
            if first:
                it = make("court", "icj", first, f"ICJ hearings: {name}", URL, end_date=last, countries=codes)
                out[it.id] = it
        elif j:
            mo = month_no(j.group(3))
            day = iso(int(j.group(4)), mo, int(j.group(2))) if mo else ""
            if day:
                it = make("court", "icj", day, f"ICJ {j.group(1).lower()}: {name}", URL, countries=codes)
                out[it.id] = it
    return list(out.values())


def fetch(today: date) -> list[CalendarItem]:
    return upcoming(parse(polite_http.get(URL)), today)
