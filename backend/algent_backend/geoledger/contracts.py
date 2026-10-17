"""
Contracts of the geospatial asset ledger: places that exist (``Asset``) and what has been said about their state
(``StatusEvent``). Docs: docs/architecture/geoledger.md.

Two rules shape everything here:

* A status is always somebody's word. ``claimant`` is required on every event, and the status vocabulary keeps
  a party's claim (``claimed_struck``) apart from damage reported or confirmed by someone else, so a claim can never
  be read as a confirmation.
* Nothing is overwritten. An asset revision and an event are appended; the current view is derived (``store``).
"""

from __future__ import annotations

import hashlib
import re
import unicodedata
from datetime import date
from typing import Literal, get_args

from pydantic import BaseModel, Field

AssetType = Literal["power_plant", "substation", "refinery", "fuel_depot", "port", "bridge", "airbase", "military_base",
                    "dam", "rail_hub", "vessel", "entity", "other"]
Precision = Literal["exact", "approximate", "city_level", "unplaced"]
Status = Literal["operational", "claimed_struck", "reported_damaged", "confirmed_damaged", "destroyed", "restored",
                 "unknown", "seized", "designated", "behaviour_flagged"]
Provenance = Literal["aggregated", "ohmega_derived"]
Confidence = Literal["low", "medium", "high"]

ASSET_TYPES: tuple[str, ...] = get_args(AssetType)
STATUSES: tuple[str, ...] = get_args(Status)
#: Statuses that describe damage or loss (a claim, a report, a confirmation): the map's warm family.
DAMAGE = ("claimed_struck", "reported_damaged", "confirmed_damaged", "destroyed")
#: Same-day tie-break when two events carry one date: the later fact wins, a confirmation beats a claim.
_RANK = {"unknown": 0, "operational": 1, "claimed_struck": 2, "reported_damaged": 3, "confirmed_damaged": 4,
         "destroyed": 5, "seized": 5, "designated": 5, "behaviour_flagged": 5, "restored": 6}


class Asset(BaseModel):
    """A place or named thing the ledger tracks. A new revision of the same ``id`` supersedes the older one."""

    id: str                                        # stable: wri-<id> | osm-<kind><id> | og-<iso>-<type>-<slug>
    name: str
    aliases: list[str] = Field(default_factory=list)
    type: AssetType = "other"
    country: str = ""                              # ISO 3166-1 alpha-2, "" when unknown
    lat: float | None = Field(None, ge=-90, le=90)
    lon: float | None = Field(None, ge=-180, le=180)
    precision: Precision = "approximate"
    attrs: dict[str, str | float | int] = Field(default_factory=dict)    # capacity_mw, fuel, owner, year, osm tags
    source: str = ""                               # where the place comes from, e.g. "WRI Global Power Plant Database v1.3"
    licence: str = ""
    source_url: str = ""
    provenance: Provenance = "aggregated"
    recorded_at: str = ""                          # when this revision was written (UTC ISO)


class StatusEvent(BaseModel):
    """One dated statement about an asset's state, by a named party. Append-only."""

    id: str
    asset_id: str
    occurred_on: str                               # YYYY-MM-DD, the day the status concerns
    occurred_at: str = ""                          # HH:MM when a source gives the hour
    status: Status
    claimant: str                                  # who says it: "Russian MoD", "Ukrenergo", "Ohmega analysis"
    confidence: Confidence = "medium"
    sources: list[str] = Field(default_factory=list)       # URLs
    provenance: Provenance = "aggregated"
    observed_at: str = ""                          # when the ledger recorded it (UTC ISO)
    note: str = ""                                 # at most NOTE_CHARS: the words it rests on
    via: str = ""                                  # how it got here: daily:<date>:<theater>, cli, backfill:<kind>:<id>


NOTE_CHARS = 240
_SLUG = re.compile(r"[^a-z0-9]+")


def fold(text: str) -> str:
    """Casefolded, accent-free form of ``text`` (names compare through this)."""
    return "".join(c for c in unicodedata.normalize("NFKD", text or "") if not unicodedata.combining(c)).casefold()


def slug(text: str, limit: int = 40) -> str:
    return _SLUG.sub("-", fold(text)).strip("-")[:limit] or "unnamed"


def new_asset_id(name: str, type_: str, country: str) -> str:
    """The stable id of a place we mint ourselves (the same facility named the same way gets the same id)."""
    return f"og-{(country or 'xx').lower()}-{type_}-{slug(name)}"


def event_id(asset_id: str, occurred_on: str, status: str, claimant: str) -> str:
    """Deterministic, so the same claim found again (tomorrow's daily, a backfill) is not stored twice."""
    key = "|".join((asset_id, occurred_on, status, " ".join(fold(claimant).split())))
    return "ev-" + hashlib.sha1(key.encode("utf-8")).hexdigest()[:16]


def valid_day(raw: str) -> bool:
    try:
        date.fromisoformat(raw)
    except ValueError:
        return False
    return bool(re.fullmatch(r"\d{4}-\d{2}-\d{2}", raw))


def latest(events: list[StatusEvent]) -> StatusEvent | None:
    """The event that describes the asset now: newest day, then newest hour, then the more advanced status. A behaviour flag (something
    Ohmega observed a vessel doing) never replaces the state of the asset itself; it describes the asset only when nothing else is on record."""
    events = [e for e in events if e.status != "behaviour_flagged"] or events
    return max(events, key=lambda e: (e.occurred_on, e.occurred_at, _RANK.get(e.status, 0), e.observed_at), default=None)
