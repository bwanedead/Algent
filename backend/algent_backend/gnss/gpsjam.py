"""
GPSJam.org (keyless) — the daily interference file, read as an independent cross-check.

``https://gpsjam.org/data/<YYYY-MM-DD>-h3_4.csv``: one row per H3 resolution-4 cell, ``hex,count_good_aircraft,count_bad_aircraft`` (~190 KB, ~48k rows).
The file is streamed row by row; a cell with at least ``GPSJAM_MIN_AIRCRAFT`` aircraft and a bad share at or above ``GPSJAM_KEEP_SHARE`` (their top band) becomes a zone, its centre
decoded by ``h3.center`` (pentagon cells are skipped). The file for a day appears the day after, so a run asks for yesterday and steps back.
"""

from __future__ import annotations

from collections.abc import Callable, Iterable
from datetime import date, timedelta

from algent_backend.polite_http import SourceError, stream_lines

from . import flags, h3
from .contracts import COVERAGE, Zone, zone_id
from .zones import country_of, severity


def parse(lines: Iterable[str], day: str, *, country: Callable[[float, float], str] = country_of) -> list[Zone]:
    out = []
    for line in lines:
        parts = line.strip().split(",")
        if len(parts) != 3 or not parts[1].isdigit() or not parts[2].isdigit():
            continue                                        # the header, or a torn row
        good, bad = int(parts[1]), int(parts[2])
        n = good + bad
        if n < flags.GPSJAM_MIN_AIRCRAFT or bad / n < flags.GPSJAM_KEEP_SHARE or bad < flags.MIN_DEGRADED:
            continue
        if (c := h3.center(parts[0])) is None:
            continue
        share = bad / n
        out.append(Zone(id=zone_id("gpsjam", day, parts[0]), date=day, source="gpsjam", cell=parts[0], lat=round(c[0], 3), lon=round(c[1], 3),
                        size_deg=flags.GPSJAM_EDGE_DEG, country=country(*c), severity=severity(share), degraded_share=round(share, 4), aircraft=n,
                        basis="third_party", coverage_note=COVERAGE["gpsjam"]))
    return sorted(out, key=lambda z: (-z.degraded_share, z.cell))


def fetch(today: date | None = None, *, lines: Callable[[str], Iterable[str]] = stream_lines) -> tuple[str, list[Zone]]:
    """(day, zones) for the newest day GPSJam has a file for; raises SourceError if none of the last few days answers."""
    today = today or date.today()
    last: Exception | None = None
    for back in range(1, flags.GPSJAM_LOOKBACK + 1):
        day = (today - timedelta(days=back)).isoformat()
        try:
            return day, parse(lines(flags.GPSJAM_URL.format(day=day)), day)
        except SourceError as exc:
            last = exc
    raise SourceError(f"GPSJam has no file for the last {flags.GPSJAM_LOOKBACK} days: {last}")
