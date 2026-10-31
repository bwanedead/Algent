"""
Elections records. One ``Snapshot`` per election per change, append-only (``store.py``): what Wikipedia's polling and election pages said when we read them.

Shares are percent or seats (``unit``) keyed by the party or candidate name as the table wrote it. A poll row that did not parse cleanly is kept as raw
cells (``uncertain``) rather than dropped or guessed. Every snapshot names its source pages (CC BY-SA 4.0) and is ``medium`` confidence: volunteer-compiled.
"""

from __future__ import annotations

import hashlib
import json
import re
from typing import Literal

from pydantic import BaseModel, Field

SCHEMA = "ohmega.elections.snapshot/1"
Unit = Literal["percent", "seats"]
ResultStatus = Literal["official", "preliminary", "unstated"]


class Poll(BaseModel):
    pollster: str
    fieldwork: str = ""                                   # as written: "20-24 Oct 2026"
    date: str = ""                                        # ISO day fieldwork ended; "" when unreadable
    sample: int | None = None
    unit: Unit = "percent"
    shares: dict[str, float] = Field(default_factory=dict)  # party or candidate -> percent or seats
    others: dict[str, float] = Field(default_factory=dict)  # undecided, others, lead...: numbers that are not a party
    uncertain: bool = False
    raw: list[str] = Field(default_factory=list)          # the cleaned cells, kept only when ``uncertain``


class PollAverage(BaseModel):
    """The mean per party over the newest polls of one table (``flags.AVERAGE_LAST_N``); a party missing from a poll is skipped, not zero."""

    unit: Unit
    n_polls: int
    first: str
    last: str
    pollsters: list[str]
    shares: dict[str, float]


class PollTable(BaseModel):
    heading: str
    unit: Unit
    n_total: int                                          # polls in the page's table (``polls`` holds the newest ``MAX_POLLS_PER_TABLE``)
    polls: list[Poll]
    average: PollAverage | None = None


class ResultRow(BaseModel):
    name: str
    party: str = ""                                       # for a candidate table
    votes: int | None = None
    percent: float | None = None
    seats: int | None = None


class Results(BaseModel):
    heading: str
    status: ResultStatus = "unstated"
    status_note: str = ""                                 # the words on the page that say so
    rows: list[ResultRow]
    totals: dict[str, float] = Field(default_factory=dict)  # total / valid / invalid / turnout rows, by name


class Snapshot(BaseModel):
    schema_: str = Field(default=SCHEMA, alias="schema")
    election: str                                         # the article title: "2026 Hungarian parliamentary election"
    slug: str
    country: str = ""                                     # ISO2 when the calendar knew it
    date: str = ""                                        # election day (calendar), "" if unknown
    via: str = "calendar"                                 # calendar | ask
    acquired_at: str
    polls: list[PollTable] = Field(default_factory=list)
    results: Results | None = None
    pages: dict[str, str] = Field(default_factory=dict)   # role (polling | election) -> article URL; only pages that exist
    license: str = "CC BY-SA 4.0"
    attribution: str = "Wikipedia contributors"
    confidence: str = "medium"

    model_config = {"populate_by_name": True}

    def digest(self) -> str:
        """A hash of what the pages said (not when we read them): an identical read appends nothing."""
        body = self.model_dump(by_alias=True, exclude={"acquired_at"})
        return hashlib.sha1(json.dumps(body, sort_keys=True, ensure_ascii=False).encode("utf-8")).hexdigest()[:16]


def slug_of(title: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", title.casefold()).strip("-")[:90]
