"""
Maritime contracts — one behaviour EVENT. Nothing here fetches or detects.

An event is Ohmega's own derivation from the AIS it hears (provenance ``ohmega_derived``): what a vessel (or a pair) did, the evidence
points it rests on, a confidence and the one-sentence reason it was flagged. It says a pattern was observed, never what it means: a
dark gap, a rename and a slow encounter all have innocent explanations, and the wording keeps that open.
"""

from __future__ import annotations

import hashlib
from datetime import datetime, timezone
from typing import Any, Literal

from pydantic import BaseModel, Field

Kind = Literal["ais_gap", "sts", "identity", "sanctioned", "loiter"]
KINDS: tuple[str, ...] = ("ais_gap", "sts", "identity", "sanctioned", "loiter")
LABEL: dict[str, str] = {"ais_gap": "AIS gap", "sts": "Ship-to-ship", "identity": "Identity change", "sanctioned": "Sanctioned vessel seen",
                         "loiter": "Loitering"}
#: One evidence point: [unix seconds, lat, lon, speed knots (-1 unknown), note].
Point = list[Any]


def iso(ts: float) -> str:
    return datetime.fromtimestamp(ts, tz=timezone.utc).isoformat(timespec="seconds")


def event_id(kind: str, *parts: object) -> str:
    """Deterministic: the same behaviour found again (a later pass, a restart) updates one event instead of adding another."""
    return "mb-" + hashlib.sha1("|".join([kind, *map(str, parts)]).encode("utf-8")).hexdigest()[:16]


class BehaviourEvent(BaseModel):
    id: str
    kind: Kind
    mmsi: int
    mmsi2: int | None = None                  # the partner of an STS pair
    name: str = ""
    name2: str = ""
    imo: str = ""
    flag: str = ""                            # ISO2, from the MMSI's MID
    flag2: str = ""
    ship_class: str = ""                      # tanker | cargo | ... (live/classify)
    started_at: str
    ended_at: str | None = None               # None = still going
    last_seen: str = ""
    state: Literal["ongoing", "ended", "unresolved"] = "ongoing"
    lat: float | None = None                  # where (the last position before a gap, the meeting point, the sighting)
    lon: float | None = None
    area: str = ""                            # the named area it lies in (a chokepoint / region label), "" otherwise
    countries: list[str] = Field(default_factory=list)      # the desk's names for the area (matched against a theater's countries)
    confidence: float = 0.0                   # 0..1
    rationale: str = ""                       # why it was flagged, in one sentence, with the numbers
    summary: str = ""                         # the plain sentence the site and the daily show
    detail: dict[str, Any] = Field(default_factory=dict)    # the numbers each detector used
    evidence: list[Point] = Field(default_factory=list)
    provenance: Literal["ohmega_derived"] = "ohmega_derived"
    updated_at: str = ""

    @property
    def active(self) -> bool:
        return self.ended_at is None
