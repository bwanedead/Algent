"""
USGS earthquakes — GeoJSON summary feed, keyless. Default: every quake of magnitude 4.5+ in the past day.

Severity comes from USGS itself: ``major`` at magnitude 7.0 or more (USGS's own class), a PAGER alert of orange or
red, or a tsunami flag; ``notable`` for a yellow alert; otherwise ``info``. The country is found by locating the
epicentre on the desk basemap, falling back to the last word of USGS's place text.
"""

from __future__ import annotations

import json
from datetime import datetime, timezone

from .. import flags, places
from ..contracts import Ctx, Feed, FeedResult, LiveEvent, from_epoch

URL = "https://earthquake.usgs.gov/earthquakes/feed/v1.0/summary/{feed}.geojson"


def parse(text: str) -> list[LiveEvent]:
    out = []
    for f in json.loads(text).get("features", []):
        p, coords = f.get("properties") or {}, (f.get("geometry") or {}).get("coordinates") or []
        if len(coords) < 2 or p.get("mag") is None:
            continue
        lon, lat = float(coords[0]), float(coords[1])
        mag, place = float(p["mag"]), str(p.get("place") or "")
        country = places.country_at(lat, lon)
        alert = p.get("alert")
        severity = ("major" if mag >= flags.MAJOR_MAGNITUDE or alert in ("orange", "red") or p.get("tsunami")
                    else "notable" if alert == "yellow" else "info")
        when = datetime.fromtimestamp(p["time"] / 1000, tz=timezone.utc)
        depth = f", {coords[2]:.0f} km deep" if len(coords) > 2 and coords[2] is not None else ""
        extra = " USGS flagged a possible tsunami." if p.get("tsunami") else ""
        out.append(LiveEvent(
            id=f"usgs:{f.get('id') or p.get('code')}", feed="usgs", kind="quake", lat=lat, lon=lon,
            countries=[country] if country else [], severity=severity,
            title=f"M{mag:.1f} earthquake, {place}" if place else f"M{mag:.1f} earthquake",
            detail=(f"A magnitude {mag:.1f} earthquake{depth} at {when.strftime('%d %b %H:%M UTC')}. "
                    f"Each whole step up in magnitude is about 32 times more energy. Early magnitudes can be revised.{extra}"),
            start=from_epoch(p["time"] / 1000), source_url=p.get("url") or "https://earthquake.usgs.gov/earthquakes/map/",
            source="USGS", tags=["quake"], data={"magnitude": mag, "depth_km": coords[2] if len(coords) > 2 else None,
                                                "alert": alert, "tsunami": bool(p.get("tsunami")), "place": place}))
    out.sort(key=lambda e: -e.data["magnitude"])
    return out


def fetch(ctx: Ctx) -> FeedResult:
    events = parse(ctx.get(URL.format(feed=flags.QUAKE_FEED)))
    return FeedResult(events=events, note=f"{len(events)} quakes in the {flags.QUAKE_FEED} feed")


FEED = Feed("usgs", "Earthquakes", "USGS", "https://earthquake.usgs.gov/earthquakes/map/", fetch)
