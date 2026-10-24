"""
Leaders' summits and conferences whose host sites are blocked, script-only or change every year (G20, COP, APEC, BRICS, CHOGM ...):
the date is read from the infobox of the event's Wikipedia page, fetched as wikitext (``action=raw``). A curated list of page titles,
because a year's title is a convention, not a rule; a title that does not exist yet is simply skipped (no redirect is followed, so a
future summit can never inherit the date of the last one). Volunteer-compiled, so graded ``announced``; the link is the page.
Only text facts (name, dates, host country) are used (CC BY-SA 4.0 page, cited by link).
"""

from __future__ import annotations

import re
from datetime import date

from algent_backend import polite_http

from ..contracts import CalendarItem, make
from . import iso, span_dates, upcoming

RAW = "https://en.wikipedia.org/w/index.php"
PAGE = "https://en.wikipedia.org/wiki/{title}"

#: (page title, label, kind, host countries). Add a row when a new year's page appears; a missing page costs nothing.
EVENTS: tuple[tuple[str, str, str, tuple[str, ...]], ...] = (
    ("2026_G20_Miami_summit", "G20 leaders' summit, Miami", "summit", ("US",)),
    ("2026_United_Nations_Climate_Change_Conference", "COP31 climate conference, Antalya", "summit", ("TR",)),
    ("APEC_China_2026", "APEC leaders' meeting, China", "summit", ("CN",)),
    ("2026_Commonwealth_Heads_of_Government_Meeting", "Commonwealth heads of government meeting", "summit", ()),
    ("18th_BRICS_summit", "BRICS leaders' summit, India", "summit", ("IN",)),
    ("2026_Ankara_NATO_summit", "NATO summit, Ankara", "summit", ("TR",)),
    ("52nd_G7_summit", "G7 leaders' summit, Evian", "summit", ("FR",)),
    ("2027_G7_summit", "G7 leaders' summit", "summit", ()),
    ("2027_NATO_summit", "NATO summit", "summit", ()),
    ("49th_ASEAN_Summit", "ASEAN summit", "summit", ()),
    ("2026_SCO_summit", "Shanghai Cooperation Organisation summit", "summit", ()),
)
_FIELD = re.compile(r"\|\s*(?:dates?|start_?date)\s*=\s*([^\n]*)", re.I)
_TMPL = re.compile(r"\{\{\s*(?:start and end dates|start date and age|start date|end date)\s*\|\s*(\d{4})\s*\|\s*(\d{1,2})\s*\|\s*(\d{1,2})(?:\s*\|\s*(\d{4})\s*\|\s*(\d{1,2})\s*\|\s*(\d{1,2}))?", re.I)


def infobox_dates(wikitext: str) -> tuple[str, str]:
    """First and last ISO day from the first ``date``/``dates`` infobox field that holds a full day ("" when none does)."""
    for m in _FIELD.finditer(wikitext):
        value = re.sub(r"<ref[^>]*?/>|<ref[^>]*>.*?</ref>", "", m.group(1), flags=re.S)
        t = _TMPL.search(value)
        if t:
            first = iso(int(t.group(1)), int(t.group(2)), int(t.group(3)))
            last = iso(int(t.group(4)), int(t.group(5)), int(t.group(6))) if t.group(4) else ""
            if first:
                return first, last
        first, last = span_dates(re.sub(r"\{\{[^{}]*\}\}|\[\[(?:[^\]|]*\|)?([^\]]*)\]\]", r"\1", value))
        if first:
            return first, last
    return "", ""


def parse(wikitext: str, title: str, label: str, kind: str, countries: tuple[str, ...]) -> list[CalendarItem]:
    if not wikitext or wikitext.lstrip().upper().startswith("#REDIRECT"):
        return []
    first, last = infobox_dates(wikitext)
    return [make(kind, "summits", first, label, PAGE.format(title=title), end_date=last, countries=list(countries), confidence="medium")] if first else []


def fetch(today: date) -> list[CalendarItem]:
    out: list[CalendarItem] = []
    for title, label, kind, countries in EVENTS:
        text = polite_http.get(RAW, params={"title": title, "action": "raw"}, missing_ok=True)
        out += parse(text, title, label, kind, countries)
    return upcoming(out, today)
