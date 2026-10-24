"""
National elections from Wikipedia's "<year> national electoral calendar" pages (wikitext via ``action=raw``).

The pages are one bullet per election date under month headings, with sub-bullets for several votes on one day, each naming the
country and the body being elected. Compiled by volunteers from official announcements, so ``medium`` confidence; the link
cited is the calendar page (CC BY-SA 4.0 text; we reuse only facts: country, office, date).
"""

from __future__ import annotations

import re
from datetime import date

from algent_backend import polite_http
from algent_backend.actors import names as cnames

from ..contracts import CalendarItem, make
from . import iso, inside, month_no

PAGE = "https://en.wikipedia.org/wiki/{year}_national_electoral_calendar"
RAW = "https://en.wikipedia.org/w/index.php?title={year}_national_electoral_calendar&action=raw"

_DAY = re.compile(r"^(\d{1,2})(?:\s+([A-Za-z]+))?\s*[–-]\s*(\d{1,2})\s+([A-Za-z]+)|^(\d{1,2})\s+([A-Za-z]+)")
_LINK = re.compile(r"\[\[(?:[^\]|]*\|)?([^\]]*)\]\]")
_VOTE = re.compile(r"referend|plebiscite|initiative|recall", re.I)
_REF = re.compile(r"<ref[^>]*?/>|<ref[^>]*>.*?</ref>", re.S)


def _clean(text: str) -> str:
    text = _REF.sub("", text)
    text = re.sub(r"\{\{[^{}]*\}\}", "", text)
    text = _LINK.sub(r"\1", text).replace("'''", "").replace("''", "")
    return " ".join(re.sub(r"<[^>]+>", "", text).split())


def _split(rest: str) -> tuple[str, str]:
    """'Brazil, President (1st round)' -> (country, office)."""
    country, _, office = rest.partition(",")
    return country.strip(), office.strip()


def _when(head: str, year: int, month_hint: int | None) -> tuple[str, str]:
    m = _DAY.match(head)
    if not m:
        return "", ""
    if m.group(3):                                                   # a range: 9–10 October / 30 September – 2 October
        m2 = month_no(m.group(4))
        m1 = month_no(m.group(2)) if m.group(2) else m2
        return (iso(year, m1, int(m.group(1))), iso(year, m2, int(m.group(3)))) if m1 and m2 else ("", "")
    mo = month_no(m.group(6))
    return (iso(year, mo, int(m.group(5))), "") if mo else ("", "")


def parse(wikitext: str, year: int) -> list[CalendarItem]:
    out: list[CalendarItem] = []
    parent_date: tuple[str, str] = ("", "")
    for raw in wikitext.splitlines():
        if not raw.startswith("*"):
            parent_date = ("", "") if not raw.startswith("*") and raw.strip() else parent_date
            continue
        depth = len(raw) - len(raw.lstrip("*"))
        body = _clean(raw.lstrip("*"))
        if depth == 1:
            head, _, rest = body.partition(":")
            parent_date = _when(head.strip(), year, None)
            rest = rest.strip()
            if not parent_date[0]:
                continue
        elif parent_date[0]:
            rest = body
        else:
            continue
        country, office = _split(rest)
        if not country:
            continue
        iso2 = cnames.iso2(country.replace("the ", "", 1) if country.startswith("the ") else country)
        title = f"{country}: {office}" if office else f"{country} election"
        kind = "vote" if _VOTE.search(office) else "election"          # referendums, plebiscites, initiatives; runoffs stay elections ("(2nd round)")
        out.append(make(kind, "elections", parent_date[0], title, PAGE.format(year=year), end_date=parent_date[1],
                        countries=[iso2] if iso2 else [], confidence="medium"))
    return out


def fetch(today: date) -> list[CalendarItem]:
    items: list[CalendarItem] = []
    for year in (today.year, today.year + 1):
        text = polite_http.get(RAW.format(year=year), missing_ok=True)
        items += parse(text, year) if text else []
    return [i for i in items if inside(i.date, today)]
