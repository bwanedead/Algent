"""
Calendar contracts — one dated upcoming item and the vocabulary around it.

An item is a fact about the future with a source: a date (or a window), a title of at most ten words, a kind, the countries it
concerns (ISO2), the theaters and situations it bears on and how far to trust it. Official schedules are ``high``; lists compiled
from press reports (elections, OPEC+) ``medium``; text we extracted from our own reports ``low``.

Additive fields (contract ohmega.calendar stays major 1): ``topic`` (the filter chip, derived from the kind), ``importance``
(1 routine .. 3 major, rule in ``rank.py``), ``grade`` (the four-level trust word: official | announced | estimated | unconfirmed)
and ``sources`` (every source that listed the same event, after ``merge.py`` dedupes across sources).
"""

from __future__ import annotations

import hashlib
import unicodedata
from typing import Literal

from pydantic import BaseModel, Field

Kind = Literal["election", "central_bank", "summit", "security_council", "opec", "deadline", "vote", "data_release", "commodity_report",
               "conference", "earnings", "regulation", "launch", "court", "market_resolves"]
KINDS: tuple[str, ...] = ("election", "central_bank", "summit", "security_council", "opec", "deadline", "vote", "data_release", "commodity_report",
                          "conference", "earnings", "regulation", "launch", "court", "market_resolves")
Confidence = Literal["high", "medium", "low"]
Grade = Literal["official", "announced", "estimated", "unconfirmed"]
GRADE_OF: dict[str, str] = {"high": "official", "medium": "announced", "low": "unconfirmed"}
GRADE_RANK: dict[str, int] = {"official": 3, "announced": 2, "estimated": 1, "unconfirmed": 0}
TOPICS: tuple[str, ...] = ("economy", "central_banks", "elections", "diplomacy", "security", "energy", "tech", "space", "markets")
#: kind -> topic chip on the site. A deadline is whatever our report called it; "diplomacy" is its honest default.
TOPIC_OF: dict[str, str] = {"election": "elections", "vote": "elections", "central_bank": "central_banks", "data_release": "economy",
                            "commodity_report": "energy", "opec": "energy", "summit": "diplomacy", "court": "diplomacy",
                            "security_council": "security", "deadline": "diplomacy", "conference": "tech", "earnings": "tech",
                            "regulation": "tech", "launch": "space", "market_resolves": "markets"}
TITLE_WORDS = 10


class CalendarItem(BaseModel):
    id: str
    date: str                                       # YYYY-MM-DD: the day, or the first day of a window
    end_date: str = ""                              # last day of a window; "" = a single day
    title: str
    kind: Kind
    countries: list[str] = Field(default_factory=list)       # ISO2
    theaters: list[str] = Field(default_factory=list)        # theater ids (extracted items, mapped markets)
    situations: list[str] = Field(default_factory=list)      # situation ids (watch horizons; linked from ids, never from prose)
    source: str                                     # the collector's key: fed | ecb | boj | elections | corpus | ...
    source_url: str
    confidence: Confidence = "high"
    grade: Grade = "official"
    topic: str = ""                                 # one of TOPICS (set by make)
    importance: int = 1                             # 1 routine, 2 notable, 3 major (rank.importance; set at publish)
    sources: list[dict[str, str]] = Field(default_factory=list)   # [{"source", "url"}] after the cross-source merge
    provenance: Literal["aggregated", "ohmega_derived"] = "aggregated"
    via: str = ""                                   # extracted items: daily:<date>:<theater>; markets: market:<id>
    active: bool = True                             # False once its source stops listing it (moved or cancelled)
    first_seen: str = ""
    updated_at: str = ""


def short(title: str, words: int = TITLE_WORDS) -> str:
    """At most ``words`` words, no trailing punctuation."""
    parts = " ".join((title or "").split()).split(" ")
    return " ".join(parts[:words]).rstrip(" ,;:-–")


def _fold(text: str) -> str:
    return "".join(c for c in unicodedata.normalize("NFKD", text.casefold()) if c.isalnum())


def item_id(kind: str, source: str, date: str, title: str) -> str:
    """Deterministic: the same item found again (tomorrow's run, another daily) is one item."""
    return "cal-" + hashlib.sha1("|".join((kind, source, date, _fold(title))).encode("utf-8")).hexdigest()[:16]


def make(kind: str, source: str, date: str, title: str, url: str, *, end_date: str = "", countries: list[str] | None = None,
         theaters: list[str] | None = None, situations: list[str] | None = None, confidence: str = "high",
         provenance: str = "aggregated", via: str = "", grade: str = "") -> CalendarItem:
    """``grade`` defaults from ``confidence`` (high official, medium announced, low unconfirmed); rule-derived dates pass "estimated"."""
    title = short(title)
    grade = grade or GRADE_OF.get(confidence, "announced")
    if grade == "estimated":
        confidence = "medium"
    return CalendarItem(id=item_id(kind, source, date, title), date=date, end_date=end_date if end_date and end_date != date else "",
                        title=title, kind=kind, countries=sorted(set(countries or [])), theaters=sorted(set(theaters or [])),   # type: ignore[arg-type]
                        situations=sorted(set(situations or [])), grade=grade, topic=TOPIC_OF.get(kind, "diplomacy"),          # type: ignore[arg-type]
                        source=source, source_url=url, confidence=confidence, provenance=provenance, via=via)             # type: ignore[arg-type]
