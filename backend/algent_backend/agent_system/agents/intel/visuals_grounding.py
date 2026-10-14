"""
The grounding rule for daily visuals: a number written by the planner (or a scene) must be in the cited facts.

Mechanical and conservative about what counts as a CLAIM. Calendar furniture is not one: ISO dates ("2026-10-08"),
a year-month ("2026-10"), written dates ("8 October", "October 8th", "8 Oct 2026"), ordinals ("3rd"),
clock times ("14:30"), years and single digits. Those are labels for WHEN, and the date itself is checked where
dates are facts (the cited ``when``), not as a quantity. Everything else must appear among the cited facts, compared
by value (``08`` is ``8``, ``12.50`` is ``12.5``).
"""

from __future__ import annotations

import re

_MONTH = (r"(?:jan(?:uary)?|feb(?:ruary)?|mar(?:ch)?|apr(?:il)?|may|june?|july?|aug(?:ust)?|sep(?:t(?:ember)?)?|"
          r"oct(?:ober)?|nov(?:ember)?|dec(?:ember)?)\.?")
_ORD = r"(?:st|nd|rd|th)"
#: Spans removed before numbers are read: whole dates first (longest), then smaller date fragments.
_DAY = r"\d{1,2}" + _ORD + "?"
_DAYS = rf"{_DAY}(?:\s?[-–]\s?{_DAY})?"        # 8 or 8-9 or 08-09
_CALENDAR = re.compile(
    rf"\b\d{{4}}-\d{{1,2}}-\d{{1,2}}\b|\b\d{{4}}-\d{{1,2}}\b|\b\d{{1,2}}/\d{{1,2}}/\d{{2,4}}\b"   # 2026-10-08, 2026-10, 10/08/2026
    rf"|\b{_DAYS}\s+(?:of\s+)?{_MONTH}(?:\s+\d{{4}})?\b"                                          # 8 October, 8-9 Oct 2026
    rf"|\b{_MONTH}\s+{_DAYS}(?:,?\s+\d{{4}})?\b"                                                  # October 8th, Oct 08-09, 2026
    rf"|\b\d{{1,2}}:\d{{2}}(?::\d{{2}})?\b"                                                       # 14:30
    rf"|\b\d+{_ORD}\b",                                                                            # 3rd, 22nd
    re.I)
_NUMBER = re.compile(r"\d[\d,]*(?:\.\d+)?%?")
_YEAR = re.compile(r"^(?:19|20)\d{2}$")


def _value(raw: str) -> str:
    """Canonical form of a number for comparison: no commas, no percent sign, no leading zeros, no trailing .0"""
    s = raw.replace(",", "").rstrip("%")
    try:
        f = float(s)
    except ValueError:
        return s
    return str(int(f)) if f == int(f) else repr(f)


def _numbers(text: str, *, drop_calendar: bool) -> list[str]:
    return _NUMBER.findall(_CALENDAR.sub(" ", text or "") if drop_calendar else text or "")


def ungrounded(text: str, corpus: str) -> list[str]:
    """Numbers written in ``text`` that appear in no cited fact. Years, single digits and calendar fragments
    (dates, day-of-month, ordinals, clock times) are not claims."""
    have = {_value(n) for n in _numbers(corpus, drop_calendar=False)}
    out = []
    for raw in _numbers(text, drop_calendar=True):
        n = raw.replace(",", "")
        if _YEAR.match(n) or len(n.rstrip("%")) <= 1 or re.fullmatch(r"0\d", n) or _value(raw) in have:
            continue
        out.append(raw)
    return out


# ── the other things a native visual (timeline, map story) may state: WHEN and WHERE ──────────────
_MONTHS = ("january", "february", "march", "april", "may", "june", "july", "august", "september", "october",
           "november", "december")
_GENERIC_PLACE = {"gulf", "strait", "sea", "ocean", "bay", "island", "islands", "river", "city", "port", "base", "north",
                  "south", "east", "west", "northern", "southern", "eastern", "western", "region", "province", "oblast",
                  "front", "line", "border", "area", "zone", "airbase", "coast", "central", "district", "the"}


def mentions_date(text: str, iso: str) -> bool:
    """Does ``text`` state the calendar date ``iso`` (YYYY-MM-DD): as ISO, or as "8 October" / "October 8th"?
    A cited fact is the ground of an event's date; the year is taken as the event's own."""
    m = re.fullmatch(r"(\d{4})-(\d{2})-(\d{2})", iso or "")
    if not m or not (1 <= int(m[2]) <= 12):
        return False
    if iso in (text or ""):
        return True
    mon, day = _MONTHS[int(m[2]) - 1], int(m[3])
    name = rf"(?:{mon}|{mon[:3]}\.?)"
    d = rf"0?{day}(?:st|nd|rd|th)?"
    return bool(re.search(rf"\b{d}\s+(?:of\s+)?{name}\b|\b{name}\s+{d}\b", text or "", re.I))


def mentions_place(text: str, place: str) -> bool:
    """Is the place one a cited fact speaks of? Any distinctive word of the name (not "Gulf", "North"...) in the text.
    A mechanical floor: the model's coordinates cannot be checked, the name it gave them for can."""
    hay = (text or "").lower()
    words = [w for w in re.findall(r"[^\W\d_]{3,}", (place or "").lower()) if w not in _GENERIC_PLACE]
    return bool(words) and any(re.search(rf"\b{re.escape(w)}", hay) for w in words)


def word_count(text: str) -> int:
    return len((text or "").split())
