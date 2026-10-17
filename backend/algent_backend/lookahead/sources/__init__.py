"""
Calendar providers. Each module has a pure ``parse(...) -> list[CalendarItem]`` (tested on saved fixtures) and ``fetch(today)``
that gets the page and returns only items inside the lookahead window. Shared date helpers live here.
"""

from __future__ import annotations

import re
from datetime import date, timedelta

#: How far ahead an item is worth listing (the page shows 30 days; central banks publish a year, elections more).
HORIZON_DAYS = 240

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


def window(today: date) -> tuple[str, str]:
    return today.isoformat(), (today + timedelta(days=HORIZON_DAYS)).isoformat()


def inside(day: str, today: date) -> bool:
    lo, hi = window(today)
    return bool(day) and lo <= day <= hi


_TAGS = re.compile(r"<[^>]+>")


def text_lines(html: str) -> list[str]:
    """A page as its visible text lines (scripts and styles dropped)."""
    import html as htmllib

    html = re.sub(r"<script.*?</script>|<style.*?</style>", "", html, flags=re.S)
    return [ln.strip() for ln in htmllib.unescape(_TAGS.sub("\n", html)).splitlines() if ln.strip()]
