"""
Sanctions contracts — one list ENTRY (a row of a source's snapshot) and one EVENT (a designation or a delisting).

An entry is what a list says now; an event is what changed between two snapshots. Nothing here fetches or parses.
Countries are ISO 3166-1 alpha-2 codes (the site draws flags from them); a name the country table cannot resolve is dropped.
"""

from __future__ import annotations

import hashlib
from typing import Literal

from pydantic import BaseModel, Field

SourceId = Literal["ofac", "uk", "eu"]
EntityType = Literal["person", "entity", "vessel", "aircraft"]
Action = Literal["designated", "delisted"]

SOURCES: dict[str, dict[str, str]] = {
    "ofac": {"label": "US Treasury OFAC (SDN list)", "page": "https://ofac.treasury.gov/recent-actions"},
    "uk": {"label": "UK Sanctions List (FCDO / OFSI)", "page": "https://www.gov.uk/government/publications/the-uk-sanctions-list"},
    "eu": {"label": "EU consolidated financial sanctions list",
           "page": "https://data.europa.eu/data/datasets/consolidated-list-of-persons-groups-and-entities-subject-to-eu-financial-sanctions"},
}


class Entry(BaseModel):
    """One listed party as a source's snapshot holds it."""

    ref: str                                        # the source's own stable id (OFAC uid, UK UniqueID, EU logicalId)
    name: str
    type: EntityType = "entity"
    programmes: list[str] = Field(default_factory=list)
    countries: list[str] = Field(default_factory=list)       # ISO2
    designated_on: str = ""                         # YYYY-MM-DD when the list states it (UK, EU), "" otherwise (OFAC)
    imo: str = ""                                   # vessels: the IMO number digits
    flag: str = ""                                  # vessels: flag state ISO2
    owner: str = ""                                 # vessels: registered owner
    url: str = ""                                   # a page for this entry when the source has one (else the list's page is cited)


class SanctionsEvent(BaseModel):
    """A change between two snapshots of one source. Append-only."""

    id: str
    source: SourceId
    action: Action
    date: str                                       # YYYY-MM-DD: the designation date when the list gives a recent one, else the day we saw it
    observed_on: str                                # YYYY-MM-DD: the day our diff saw it
    ref: str
    name: str
    type: EntityType
    programmes: list[str] = Field(default_factory=list)
    countries: list[str] = Field(default_factory=list)
    imo: str = ""
    flag: str = ""
    owner: str = ""
    source_url: str
    baseline: bool = False                          # found in a source's FIRST snapshot (a recent designation the list dates itself)


def event_id(source: str, action: str, ref: str, date: str) -> str:
    """Deterministic: the same change found twice (a re-run, a restored snapshot) is stored once."""
    return "sx-" + hashlib.sha1("|".join((source, action, ref, date)).encode("utf-8")).hexdigest()[:16]
