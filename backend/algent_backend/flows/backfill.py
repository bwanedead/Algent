"""
Backfill — replay the maritime profile book's thin position history (an hourly sample per moving vessel, the last
``maritime.flags.PROFILE_KEEP_S`` = 4 days) through a fresh tracker, so the lane picture starts with days rather than minutes.

Only into an EMPTY tracker (replaying over live counts would count the same crossings twice). The book's samples are an hour apart, so
tight chokepoints are seen less reliably than by the live cycle; the days backfilled are marked as watched for the span the samples
cover and the rates they give are read the same way as live ones.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any

from algent_backend.maritime.profile import ProfileBook

from .classes import flow_class
from .tracker import LaneTracker, day_of


def _watch_span(tracker: LaneTracker, t0: float, t1: float) -> None:
    """Credit the tracker with having watched [t0, t1], split over the UTC days it covers."""
    day = datetime.fromtimestamp(t0, tz=timezone.utc).replace(hour=0, minute=0, second=0, microsecond=0)
    while day.timestamp() < t1:
        start, end = max(t0, day.timestamp()), min(t1, (day + timedelta(days=1)).timestamp())
        tracker._day(start)["secs"] += max(0.0, end - start)       # noqa: SLF001 - same package, one owner of the day records
        day += timedelta(days=1)


def from_book(book: ProfileBook, tracker: LaneTracker) -> dict[str, Any]:
    """Replay every trade carrier's samples (oldest first per vessel). Returns a small account."""
    if tracker.days or tracker.last:
        return {"skipped": "the tracker already holds counts; backfill only seeds an empty one"}
    t0, t1, vessels, hops = None, None, 0, 0
    for p in book.profiles.values():
        cls = flow_class(p.ship_type, p.name)
        if cls is None:
            continue
        pts = p.points()
        if not pts:
            continue
        vessels += 1
        for ts, lat, lon, _sog in pts:
            hops += tracker.observe(p.mmsi, lat, lon, ts, lambda c=cls: c)
            t0 = ts if t0 is None else min(t0, ts)
            t1 = ts if t1 is None else max(t1, ts)
    if t0 is not None and t1 is not None:
        _watch_span(tracker, t0, t1)
    return {"vessels": vessels, "hops": hops, "from": day_of(t0) if t0 else None, "to": day_of(t1) if t1 else None}
