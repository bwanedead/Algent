"""
Conflict event contracts — one normalised event, whatever source reported it. Nothing here fetches or parses.

``basis`` says what kind of record it is, so the site can say so next to any number built from it:
``official`` (a publishing organisation's own report, e.g. a UN agency on ReliefWeb), ``third_party`` (another project's coding: ACLED, UCDP,
GDELT) or ``our_count`` (something we counted ourselves). Every conflict source is partial, so ``coverage_note`` states the limit in words.
``coding`` is how the event was made: ``machine`` (software read news text: noisy), ``curated`` (people checked it) or ``report`` (a published
report). Countries are ISO 3166-1 alpha-2; a place we cannot resolve is "" rather than guessed.
"""

from __future__ import annotations

import hashlib
from typing import Literal

from pydantic import BaseModel, Field

SourceId = Literal["gdelt", "reliefweb", "acled", "ucdp"]
EventType = Literal["bombing", "airstrike", "armed_clash", "assault", "mass_violence", "report"]
Basis = Literal["official", "third_party", "our_count"]
Coding = Literal["machine", "curated", "report"]
Confidence = Literal["low", "medium", "high"]

SOURCES: dict[str, dict[str, str]] = {
    "gdelt": {"label": "GDELT 2.0 events (machine-coded from news)", "page": "https://www.gdeltproject.org/data.html"},
    "reliefweb": {"label": "ReliefWeb humanitarian reports (UN OCHA)", "page": "https://reliefweb.int/"},
    "acled": {"label": "ACLED (Armed Conflict Location & Event Data)", "page": "https://acleddata.com/"},
    "ucdp": {"label": "UCDP Georeferenced Event Dataset (candidate events)", "page": "https://ucdp.uu.se/"},
}

COVERAGE: dict[str, str] = {
    "gdelt": "Machine-coded from news text: it can duplicate an event, misplace it or misread it, and it only sees what media report. A floor, not a census.",
    "reliefweb": "A published humanitarian report, not an event count. Covers crises that agencies report on; locations are country-level.",
    "acled": "Curated by researchers from media and local partners; the most reliable of these sources, but reporting lags and some areas are thinly covered.",
    "ucdp": "Candidate events checked by UCDP researchers; fatality figures are best estimates and may be revised.",
}

TYPE_LABEL: dict[str, str] = {"bombing": "Bombing", "airstrike": "Air or drone strike", "armed_clash": "Armed clash", "assault": "Assault or killing",
                              "mass_violence": "Mass violence", "report": "Report"}


class AssetRef(BaseModel):
    """A geoledger asset within a few km of the event: where the event may have hit something we track."""

    id: str
    name: str
    type: str
    km: float


class ConflictEvent(BaseModel):
    id: str
    source: SourceId
    date: str                                       # YYYY-MM-DD: the day of the event (GDELT: the day it was reported)
    observed_at: str                                # UTC ISO: when we stored it
    type: EventType
    key: str = ""                                   # the dedupe key (type, actors, place): the same across days, unlike the id
    code: str = ""                                  # the source's own code (CAMEO event code, ACLED sub-event type)
    lat: float | None = Field(None, ge=-90, le=90)
    lon: float | None = Field(None, ge=-180, le=180)
    place: str = ""
    country: str = ""                               # ISO2 or ""
    actor1: str = ""
    actor2: str = ""
    fatalities: int | None = None                   # None = the source does not say (GDELT never does)
    articles: int = 1                               # reports behind it (GDELT: articles; others 1)
    title: str = ""
    urls: list[str] = Field(default_factory=list)
    coding: Coding
    confidence: Confidence
    basis: Basis
    coverage_note: str = ""
    assets: list[AssetRef] = Field(default_factory=list)


def event_id(source: str, key: str, date: str) -> str:
    """Deterministic: the same event found again (a re-run, a later file, a restored shard) keeps one id."""
    return "cx-" + hashlib.sha1(f"{source}|{key}|{date}".encode()).hexdigest()[:16]


def neighbour_ids(source: str, key: str, date: str, days: int) -> list[str]:
    """The ids the same event would carry if it were dated up to ``days`` either side: a re-report a day later is the same event."""
    from datetime import date as _d, timedelta

    d0 = _d.fromisoformat(date)
    return [event_id(source, key, (d0 + timedelta(days=k)).isoformat()) for k in range(-days, days + 1)]
