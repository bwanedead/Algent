"""
GDELT 2.0 events (keyless) — the 15-minute export files, filtered to violence, geolocated, deduplicated.

``lastupdate.txt`` names the newest file; files are ``YYYYMMDDHHMMSS.export.CSV.zip`` every 15 minutes, 61 tab-separated columns, no header.
We keep CAMEO root codes 18 (assault), 19 (fight), 20 (mass violence) whose action is geocoded to a city or ADM1 and reported by at least
``GDELT_MIN_ARTICLES`` articles. Rows of one file describing the same thing (same type, actors and place) merge, summing their articles.
GDELT is MACHINE-CODED: it duplicates, misplaces and misreads. Events say so (``coding=machine``, low or medium confidence) and never carry fatalities.
"""

from __future__ import annotations

import io
import tempfile
import zipfile
from collections.abc import Iterable
from datetime import UTC, datetime, timedelta
from pathlib import Path

from algent_backend.polite_http import SourceError, download, get

from .. import fips, flags
from ..contracts import COVERAGE, ConflictEvent, event_id

BASE = "https://data.gdeltproject.org/gdeltv2/"
LATEST = BASE + "lastupdate.txt"

# column indexes of the GDELT 2.0 events table
C_ACTOR1_CODE, C_ACTOR1_NAME, C_ACTOR2_CODE, C_ACTOR2_NAME = 5, 6, 15, 16
C_DAY, C_BASE, C_ROOT = 1, 27, 28
C_ARTICLES = 33
C_GEO_TYPE, C_GEO_NAME, C_GEO_CC, C_LAT, C_LON, C_FEATURE = 51, 52, 53, 56, 57, 58
C_URL, N_COLS = 60, 61


def kind_of(base_code: str) -> str:
    """The normalised type of a CAMEO event code (its first three digits are the family)."""
    c = (base_code or "")[:3]
    if c.startswith("20"):
        return "mass_violence"
    if c == "183":
        return "bombing"
    if c == "195":
        return "airstrike"
    if c.startswith("19"):
        return "armed_clash"
    return "assault"


def parse(lines: Iterable[str], observed_at: str) -> list[ConflictEvent]:
    """Violence rows of one export file as merged, capped events. Pure: no I/O."""
    merged: dict[str, ConflictEvent] = {}
    for line in lines:
        f = line.rstrip("\r\n").split("\t")
        if len(f) < N_COLS or f[C_ROOT] not in flags.GDELT_ROOTS or f[C_GEO_TYPE] not in flags.GDELT_GEO_TYPES:
            continue
        try:
            lat, lon, arts = float(f[C_LAT]), float(f[C_LON]), max(1, int(f[C_ARTICLES] or 1))
            day = f"{f[C_DAY][:4]}-{f[C_DAY][4:6]}-{f[C_DAY][6:8]}"
            datetime.fromisoformat(day)
        except ValueError:
            continue                                        # a row with no usable number or date is not an event we can place
        kind = kind_of(f[C_BASE])
        key = "|".join((kind, f[C_ACTOR1_CODE], f[C_ACTOR2_CODE], f[C_FEATURE] or f"{lat:.2f},{lon:.2f}"))
        url = f[C_URL].strip()
        if (prev := merged.get(key)) is not None:
            prev.articles += arts
            if url and url not in prev.urls and len(prev.urls) < flags.MAX_URLS:
                prev.urls.append(url)
            continue
        place = f[C_GEO_NAME].strip()
        merged[key] = ConflictEvent(
            id=event_id("gdelt", key, day), source="gdelt", date=day, observed_at=observed_at, type=kind, code=f[C_BASE],
            lat=round(lat, 4), lon=round(lon, 4), place=place, country=fips.iso2(f[C_GEO_CC]),
            actor1=f[C_ACTOR1_NAME].title(), actor2=f[C_ACTOR2_NAME].title(), articles=arts, urls=[url] if url else [],
            key=key, coding="machine", confidence="low", basis="third_party", coverage_note=COVERAGE["gdelt"], title=place)
    keep = [e for e in merged.values() if e.articles >= flags.GDELT_MIN_ARTICLES]
    keep.sort(key=lambda e: -e.articles)
    for e in keep:
        e.confidence = "medium" if e.articles >= flags.GDELT_MEDIUM_ARTICLES else "low"
    return keep[: flags.GDELT_MAX_PER_FILE]


def latest_stamp() -> str:
    for line in get(LATEST).splitlines():
        if ".export." in line:
            return line.split()[-1].rsplit("/", 1)[-1].split(".")[0]
    raise SourceError("lastupdate.txt names no export file")


def stamps_after(cursor: str, latest: str) -> list[str]:
    """The 15-minute stamps after ``cursor`` up to ``latest`` (at most the catch-up bound, newest ones)."""
    fmt = "%Y%m%d%H%M%S"
    out, t = [], datetime.strptime(latest, fmt)
    stop = datetime.strptime(cursor, fmt) if cursor else t - timedelta(minutes=15)
    while t > stop and len(out) < flags.GDELT_CATCHUP_FILES:
        out.append(t.strftime(fmt))
        t -= timedelta(minutes=15)
    return sorted(out)


def fetch_file(stamp: str) -> list[ConflictEvent]:
    """Download one export file (a ~60 KB zip) and parse it; the zip is streamed to a temporary file and read line by line."""
    observed = datetime.now(UTC).isoformat(timespec="seconds")
    with tempfile.TemporaryDirectory(prefix="gdelt_") as tmp:
        path = download(f"{BASE}{stamp}.export.CSV.zip", Path(tmp) / "x.zip")
        with zipfile.ZipFile(path) as z, z.open(z.namelist()[0]) as raw:
            return parse(io.TextIOWrapper(raw, encoding="utf-8", errors="replace"), observed)
