"""
Calendar contracts — one dated upcoming item and the vocabulary around it.

An item is a fact about the future with a source: a date (or a window), a title of at most ten words, a kind, the countries it
concerns (ISO2), the theaters whose daily mentioned it (extracted items only) and how far to trust it. Official schedules are
``high``; lists compiled from press reports (elections, OPEC+) ``medium``; text we extracted from our own reports ``low``.
"""

from __future__ import annotations

import hashlib
import unicodedata
from typing import Literal

from pydantic import BaseModel, Field

Kind = Literal["election", "central_bank", "summit", "security_council", "opec", "deadline", "vote"]
KINDS: tuple[str, ...] = ("election", "central_bank", "summit", "security_council", "opec", "deadline", "vote")
Confidence = Literal["high", "medium", "low"]
TITLE_WORDS = 10


class CalendarItem(BaseModel):
    id: str
    date: str                                       # YYYY-MM-DD: the day, or the first day of a window
    end_date: str = ""                              # last day of a window; "" = a single day
    title: str
    kind: Kind
    countries: list[str] = Field(default_factory=list)       # ISO2
    theaters: list[str] = Field(default_factory=list)        # theater ids (extracted items)
    source: str                                     # fed | ecb | boe | elections | unsc | opec | corpus
    source_url: str
    confidence: Confidence = "high"
    provenance: Literal["aggregated", "ohmega_derived"] = "aggregated"
    via: str = ""                                   # extracted items: daily:<date>:<theater>
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
         theaters: list[str] | None = None, confidence: str = "high", provenance: str = "aggregated", via: str = "") -> CalendarItem:
    title = short(title)
    return CalendarItem(id=item_id(kind, source, date, title), date=date, end_date=end_date if end_date and end_date != date else "",
                        title=title, kind=kind, countries=sorted(set(countries or [])), theaters=sorted(set(theaters or [])),   # type: ignore[arg-type]
                        source=source, source_url=url, confidence=confidence, provenance=provenance, via=via)             # type: ignore[arg-type]
