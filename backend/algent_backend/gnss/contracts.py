"""
GNSS contracts — one interference ZONE (a grid cell on a day). Nothing here fetches or parses.

``source`` is who says so: ``ohmega_adsb`` (our own derivation from the navigation integrity aircraft broadcast: ``basis`` our_estimate, a minimum
because we only see aircraft that volunteer receivers hear and only where we sample) or ``gpsjam`` (GPSJam.org's daily file: ``third_party``).
``flag`` marks a zone that is new or intensifying against that cell's own history (``baseline_since`` says since when we have been watching).
"""

from __future__ import annotations

import hashlib
from typing import Literal

from pydantic import BaseModel

Source = Literal["ohmega_adsb", "gpsjam"]
Severity = Literal["low", "medium", "high"]
Flag = Literal["", "new", "intensifying"]
Basis = Literal["our_estimate", "third_party"]

COVERAGE: dict[str, str] = {
    "ohmega_adsb": ("Ohmega's own estimate from ADS-B navigation accuracy (NACp) as heard by volunteer receivers, sampled hourly around known trouble "
                    "spots. It only sees aircraft that broadcast ADS-B and are heard, and only where we sample, so it is a minimum; a cell with few "
                    "aircraft is not scored."),
    "gpsjam": ("GPSJam.org's daily map built from the same ADS-B accuracy field across the world's receivers; their method and cut-offs, "
               "not ours. Used to cross-check our own estimate."),
}


class Zone(BaseModel):
    id: str
    date: str                                       # YYYY-MM-DD (UTC day of the samples)
    source: Source
    cell: str                                       # "lat,lon" of the south-west corner (ohmega_adsb) or the H3 index (gpsjam)
    lat: float                                      # cell centre
    lon: float
    size_deg: float
    country: str = ""                               # ISO2 of the land under the centre, "" at sea
    severity: Severity
    degraded_share: float                           # 0..1
    aircraft: int                                   # observations behind the share
    flag: Flag = ""
    cross_check: str = ""                           # ohmega_adsb zones: "agrees" if GPSJam shows elevated interference in the cell, "not_in_gpsjam" if not
    basis: Basis
    coverage_note: str = ""
    baseline_since: str = ""                        # the first day this source was collected (YYYY-MM-DD); "" for gpsjam


def zone_id(source: str, day: str, cell: str) -> str:
    return "gz-" + hashlib.sha1(f"{source}|{day}|{cell}".encode()).hexdigest()[:16]
