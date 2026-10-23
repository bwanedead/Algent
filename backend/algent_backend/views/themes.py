"""
The theme rule for the globe and the country panel: which theme a headline reads as, and how much it weighs.

The one home of a rule the site used to compute per request (``lib/globe/themes.ts`` + ``lib/visual.ts categoryOf``). Classification is a reading aid,
not a claim: the first matching group wins, anything unmatched is "politics". Every item that names a country adds ``base * 0.5 ** (age_days / 7)``
to that theme's tally; the country's theme is the maximum, ties going to ``THEMES`` order. ``tests/test_views_themes.py`` pins the rules to examples.
"""

from __future__ import annotations

import re
from datetime import UTC, datetime

from . import flags

#: Order is the tie-break order (and the legend order the client draws).
THEMES = ("conflict", "economy", "energy", "politics", "tech", "disaster")

_CATEGORY_RULES = (
    ("disaster", re.compile(r"\b(earthquake|quake|flood|hurricane|typhoon|cyclone|wildfire|drought|famine|outbreak|epidemic|volcano|tsunami|disaster)\b", re.I)),
    ("energy", re.compile(r"\b(oil|gas|lng|opec|pipeline|refiner\w*|hormuz|tanker|nuclear power|power grid|electricity|energy|fuel)\b", re.I)),
    ("conflict", re.compile(r"\b(war|strikes?|missiles?|military|ceasefire|troops|invasion|attack\w*|drone|armed|battle|insurgen\w*|houthi|confrontation|standoff|nuclear)\b", re.I)),
    ("economy", re.compile(r"\b(tariffs?|trade|sanctions?|economy|economic|market|inflation|debt|bank|currency|chips?|semiconductor|export controls?|supply chain)\b", re.I)),
)
_TECH = re.compile(r"\b(cyber\w*|hack\w*|ransomware|malware|breach|ai|artificial intelligence|semiconductors?|chips?|satellites?|spyware|telecom\w*|5g|data centers?|quantum|surveillance tech|internet shutdown)\b", re.I)
_POLITICS = re.compile(r"\b(election\w*|vote\w*|summit|talks|diplomat\w*|minister\w*|treaty|parliament|president\w*|government|coalition|alliance|embassy|envoy|protest\w*|coup|referendum)\b", re.I)
_DISASTER_EXTRA = re.compile(r"\b(refugees?|humanitarian|displaced|aid|cholera|earthquake|flood\w*)\b", re.I)


def category_of(*texts: str) -> str:
    s = " ".join(texts)
    for name, rx in _CATEGORY_RULES:
        if rx.search(s):
            return name
    return "politics"


def theme_of(*texts: str) -> tuple[str, float]:
    """(theme, base weight): 1 for a keyword-classified text, 0.5 for one that matched nothing and fell to the "politics" default."""
    s = " ".join(texts)
    if _TECH.search(s):
        return "tech", 1.0
    if _DISASTER_EXTRA.search(s):
        return "disaster", 1.0
    c = category_of(s)
    return c, (0.5 if c == "politics" and not _POLITICS.search(s) else 1.0)


def decay(age_days: float) -> float:
    return 0.5 ** (max(0.0, age_days) / flags.HALF_LIFE_DAYS)


def dominant(tally: dict[str, float]) -> str | None:
    """The theme with the largest tally (ties: ``THEMES`` order); None when nothing was classified."""
    best, weight = None, 0.0
    for t in THEMES:
        w = tally.get(t, 0.0)
        if w > weight:
            best, weight = t, w
    return best


def ms(iso: str) -> float | None:
    """Epoch milliseconds of an ISO time or bare day, None when unreadable."""
    if not iso:
        return None
    try:
        d = datetime.fromisoformat(iso.replace("Z", "+00:00"))
    except ValueError:
        return None
    if d.tzinfo is None:
        d = d.replace(tzinfo=UTC)
    return d.timestamp() * 1000
