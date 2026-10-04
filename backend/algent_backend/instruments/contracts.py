"""
Instruments contracts — what a measured series is, and what one reading of it is.

A ``Series`` is catalog metadata (where the number comes from, what it is about); an
``Observation`` is one reading with its provenance. Nothing here fetches or interprets: the
numbers layer is programmatic end to end (no model), so these two types are the whole vocabulary
the store, the moves math and the consumers share.

``tags`` are how a situation finds its numbers: a region/actor/dynamic vocabulary ("hormuz",
"iran", "shipping", "energy") matched against whatever a desk is working on. They are plain
lowercase keywords, not an ontology — adding a tag costs nothing and breaks nothing.
"""

from __future__ import annotations

from datetime import date, datetime, timezone
from typing import Any, Literal

from pydantic import BaseModel, Field

Frequency = Literal["daily", "weekly", "monthly"]


class Series(BaseModel):
    id: str                                   # stable key, e.g. "chk_hormuz_transits" (also the store filename)
    name: str                                 # reader-facing label
    unit: str                                 # "ships/day", "USD/bbl", "%" ...
    frequency: Frequency
    source: str                               # who publishes it, human-readable ("IMF PortWatch")
    source_url: str                           # human-readable page to cite (NOT the API endpoint)
    fetcher: str                              # provider module in ``sources/``
    params: dict[str, Any] = Field(default_factory=dict)   # provider-specific selector (port, symbol, ...)
    tags: list[str] = Field(default_factory=list)
    licence: str = ""                         # what we know about reuse terms
    public_display: bool = True               # False = internal signal until terms are reviewed


class Observation(BaseModel):
    series_id: str
    period: str                               # "YYYY-MM-DD" (daily/weekly) or "YYYY-MM" (monthly)
    value: float
    fetched_at: str                           # ISO-8601 UTC when we read it
    source_url: str
    revised: bool = False                     # True when this line replaced an earlier value for the period


def period_date(period: str) -> date:
    """A period label as a date; a month is anchored to its first day."""
    return date.fromisoformat(period if len(period) == 10 else period + "-01")


def now_iso() -> str:
    """UTC timestamp for ``Observation.fetched_at`` (one definition, so tests can patch it)."""
    return datetime.now(timezone.utc).isoformat(timespec="seconds")
