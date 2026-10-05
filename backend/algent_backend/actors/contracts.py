"""
Actors contracts — what an indicator is, and what one reading of it is.

An ``Indicator`` is catalog metadata (which source publishes it, what it measures, how to show it); an
``Observation`` is one country's value for one year with its provenance. ``Leaders`` is a dated
snapshot of who holds the two top offices. Nothing here fetches or interprets.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Literal

from pydantic import BaseModel

Group = Literal["people", "economy", "trade", "energy", "military"]
#: How a value is displayed: a count of people, US dollars, a share (%), TWh of energy, kWh per person, km2, a bare number.
Unit = Literal["people", "usd", "pct", "twh", "kwh", "km2", "persons", "months", "number"]


class Indicator(BaseModel):
    id: str                  # stable key, e.g. "gdp_pc" (names the store file; cited by consumers)
    source: str              # key in ``catalog.SOURCES``: "wb" | "owid" | "imf"
    code: str                # the source's own code (WB indicator, OWID column, IMF series)
    label: str               # reader-facing
    unit: Unit
    group: Group


class Observation(BaseModel):
    iso2: str
    indicator: str
    year: int
    value: float
    source: str              # the source key
    source_url: str
    fetched_at: str
    revised: bool = False    # True when this line replaced an earlier value for (iso2, year)


class Official(BaseModel):
    name: str
    since: str = ""          # ISO date the office was taken up, when the source says
    id: str = ""             # the source's entity id (Wikidata Q-id)


class Leaders(BaseModel):
    iso2: str
    head_of_state: Official | None = None
    head_of_government: Official | None = None
    fetched_at: str
    source_url: str


class TradeShare(BaseModel):
    """One line of a ranking: a product group or a partner country, its value in US dollars."""
    id: str                  # product group code ("27-27_Fuels") or partner ISO2
    name: str
    value: float


class TradeRanking(BaseModel):
    """A country's merchandise exports or imports for one year, ranked: product groups and partner countries,
    largest first, with the year's total. The lists are the full ranking (a handful of lines); consumers cut."""
    iso2: str
    year: int
    flow: Literal["exports", "imports"]
    total: float
    products: list[TradeShare]
    partners: list[TradeShare]
    source: str
    source_url: str
    fetched_at: str
    revised: bool = False


def now_iso() -> str:
    """UTC timestamp for ``fetched_at`` (one definition, so tests can patch it)."""
    return datetime.now(timezone.utc).isoformat(timespec="seconds")
