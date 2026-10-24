"""
Calendar providers. Each module has a pure ``parse(...) -> list[CalendarItem]`` (tested on saved fixtures) and ``fetch(today)``
that gets the page and returns only items inside the lookahead window. Shared date helpers live here.
"""

from __future__ import annotations

import re
from datetime import date, timedelta

#: The rolling window (docs/architecture/sanctions-calendar.md): 14 days back for context, 180 ahead. Ahead because the slowest cadence worth
#: planning on is a half-year (two central-bank cycles, one summit season); beyond it dates are announcements nobody has confirmed yet.
HORIZON_DAYS = 180
LOOKBACK_DAYS = 14

MONTHS = {m: i for i, m in enumerate(["january", "february", "march", "april", "may", "june", "july", "august", "september",
                                       "october", "november", "december"], 1)}
MONTHS.update({m[:3]: i for m, i in list(MONTHS.items())})
MONTHS["sept"] = 9


def month_no(word: str) -> int | None:
    return MONTHS.get(word.strip(". ").casefold())


def iso(y: int, m: int, d: int) -> str:
    try:
        return date(y, m, d).isoformat()
    except ValueError:
        return ""


def span_dates(text: str) -> tuple[str, str]:
    """First and last ISO day of a written date: "14–15 December 2026", "November 18 – 19, 2026", "30 Sep - 2 Oct 2026", "7 September
    2026", "Sep. 7, 2026". ("", "") when none is readable; the last day is "" for a single day. The year must be in the text."""
    t = " ".join(re.sub(r"\([^)]*\)", "", text).replace("–", "-").replace("—", "-").replace("\xa0", " ").split())
    m = re.search(r"(\d{1,2})(?:\s+([A-Za-z]{3,9})\.?)?\s*-\s*(\d{1,2})\s+([A-Za-z]{3,9})\.?,?\s+(\d{4})", t)
    if m:
        m2, m1 = month_no(m.group(4)), month_no(m.group(2) or m.group(4))
        return (iso(int(m.group(5)), m1, int(m.group(1))), iso(int(m.group(5)), m2, int(m.group(3)))) if m1 and m2 else ("", "")
    m = re.search(r"([A-Za-z]{3,9})\.?\s+(\d{1,2})\s*-\s*(?:([A-Za-z]{3,9})\.?\s+)?(\d{1,2}),?\s+(\d{4})", t)
    if m:
        m1, m2 = month_no(m.group(1)), month_no(m.group(3) or m.group(1))
        return (iso(int(m.group(5)), m1, int(m.group(2))), iso(int(m.group(5)), m2, int(m.group(4)))) if m1 and m2 else ("", "")
    m = re.search(r"(\d{1,2})\s+([A-Za-z]{3,9})\.?,?\s+(\d{4})", t)
    if m and month_no(m.group(2)):
        return iso(int(m.group(3)), month_no(m.group(2)), int(m.group(1))), ""
    m = re.search(r"([A-Za-z]{3,9})\.?\s+(\d{1,2}),?\s+(\d{4})", t)
    if m and month_no(m.group(1)):
        return iso(int(m.group(3)), month_no(m.group(1)), int(m.group(2))), ""
    return "", ""


def window(today: date) -> tuple[str, str]:
    return today.isoformat(), (today + timedelta(days=HORIZON_DAYS)).isoformat()


def inside(day: str, today: date) -> bool:
    lo, hi = window(today)
    return bool(day) and lo <= day <= hi


_TAGS = re.compile(r"<[^>]+>")


def upcoming(items: list, today: date) -> list:
    """The items that fall in today..today+HORIZON (a window counts by its last day, so a running meeting is still listed)."""
    lo, hi = window(today)
    return [i for i in items if (i.end_date or i.date) >= lo and i.date <= hi]


def plain(html: str) -> str:
    """One cell of markup as plain text (tags and entities dropped, white space collapsed)."""
    import html as htmllib

    return " ".join(htmllib.unescape(_TAGS.sub(" ", html)).replace("\xa0", " ").split())


def text_lines(html: str) -> list[str]:
    """A page as its visible text lines (scripts and styles dropped)."""
    import html as htmllib

    html = re.sub(r"<script.*?</script>|<style.*?</style>", "", html, flags=re.S)
    return [ln.strip() for ln in htmllib.unescape(_TAGS.sub("\n", html)).splitlines() if ln.strip()]
