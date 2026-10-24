"""
Calendar as desk input — the ``COMING UP`` block a section writer sees.

Same stance as ``live/desk.py`` and the grid block: sensing decides which countries a theater stands behind
(``sensing.corroborated``) and which items already name the theater; this module only knows the store. An item is shown when it
names the theater (an extraction from its own earlier daily) or concerns one of its countries. Reads the local store only.
"""

from __future__ import annotations

from datetime import date

from . import rank, store
from .contracts import CalendarItem

DAYS = 14
LINES = 10

_HEAD = ("COMING UP - dated items in the next {days} days that touch this theater: published central-bank, election, UN Security Council and OPEC+ "
         "schedules, and deadlines or meetings Ohmega's earlier reports named. A date is a plan, not an outcome: write them as upcoming, never as having happened. "
         "Items marked EARLIER REPORT were extracted from our own past sections and are unconfirmed:")


def _line(i: CalendarItem) -> str:
    when = i.date if not i.end_date else f"{i.date} to {i.end_date}"
    tag = "EARLIER REPORT, unconfirmed" if i.source == "corpus" else f"{i.kind.replace('_', ' ')}, {i.confidence} confidence"
    return f"- {when}: {i.title} ({tag}) {i.source_url}"


def touching(countries: set[str], theater_id: str, today: date, days: int = DAYS) -> list[CalendarItem]:
    return [i for i in store.upcoming(today, days) if rank.base(i) >= 2 and (theater_id in i.theaters or (countries & set(i.countries)))]


def for_theater(countries: set[str], theater_id: str, today: date, days: int = DAYS, limit: int = LINES) -> tuple[str, set[str], int]:
    """(text, citable source urls, n lines) — '' when nothing is coming up. Our own earlier reports are not cited as sources."""
    hit = touching(countries, theater_id, today, days)[:limit]
    if not hit:
        return "", set(), 0
    return ("\n".join([_HEAD.format(days=days), *map(_line, hit)]), {i.source_url for i in hit if i.source != "corpus"}, len(hit))


def rows(countries: set[str], theater_id: str, today: date, days: int = DAYS, limit: int = LINES) -> list[dict]:
    """The same items as compact dicts, stored on the daily's section so an archived report keeps the day's picture."""
    return [{"date": i.date, "end_date": i.end_date, "title": i.title, "kind": i.kind, "countries": i.countries, "confidence": i.confidence,
             "source": i.source, "url": i.source_url} for i in touching(countries, theater_id, today, days)[:limit]]
