"""
IODA (Georgia Tech) — country-level internet disruptions, keyless.

``/v2/outages/events?entityType=country`` lists detected outages (start, duration, which measurement caught it:
``bgp`` routing visibility, ``ping-slash24`` active probing, ``merit-nt`` network telescope). One country can have
several rows (one per measurement); we merge them into ONE event per country: earliest start, latest end, and
``major`` when two or more independent measurements agree (corroboration, not a threshold). Ongoing = ended no
earlier than ``OUTAGE_END_SLACK_S`` ago. Dashboard link per country: ioda.inetintel.cc.gatech.edu/country/XX.
"""

from __future__ import annotations

import json
from collections import defaultdict
from datetime import datetime, timezone

from .. import flags, places
from ..contracts import Ctx, Feed, FeedResult, LiveEvent, from_epoch

API = "https://api.ioda.inetintel.cc.gatech.edu/v2/outages/events"
DASHBOARD = "https://ioda.inetintel.cc.gatech.edu/country/{code}"
WINDOW_S = 86400
_MEASURE = {"bgp": "routing (BGP) visibility", "ping-slash24": "active probing", "merit-nt": "network-telescope traffic",
            "gnip": "traffic", "uc-ucsd": "traffic"}


def parse(text: str, now: datetime) -> list[LiveEvent]:
    rows = (json.loads(text).get("data") or [])
    by_country: dict[str, list[dict]] = defaultdict(list)
    for r in rows:
        loc = str(r.get("location", ""))
        if loc.startswith("country/") and r.get("start") is not None and r.get("duration") is not None:
            by_country[loc.split("/", 1)[1]].append(r)
    out = []
    for code, group in by_country.items():
        start = min(r["start"] for r in group)
        end = max(r["start"] + r["duration"] for r in group)
        ongoing = end >= now.timestamp() - flags.OUTAGE_END_SLACK_S
        sources = sorted({str(r.get("datasource")) for r in group})
        name = group[0].get("location_name") or code
        country = places.by_code(code)
        lat, lon = places.centroid(country) if country else (None, None)
        seen = ", ".join(_MEASURE.get(s, s) for s in sources)
        since = datetime.fromtimestamp(start, tz=timezone.utc).strftime("%d %b %H:%M UTC")
        out.append(LiveEvent(
            id=f"ioda:{code}:{start}", feed="ioda", kind="outage", lat=lat, lon=lon, countries=[name],
            title=f"Internet disruption in {name}" + ("" if ongoing else " (ended)"),
            detail=(f"Internet traffic to and from {name}, measured from outside the country, fell well below its normal level "
                    f"since {since}" + (" and has not recovered." if ongoing else f", and recovered by {from_epoch(end)[11:16]} UTC.")
                    + f" Caught by: {seen}. A shutdown ordered by a government, a cut cable, a power failure or a disaster all look "
                      "like this; the measurement alone does not say which."),
            severity="major" if len(sources) >= 2 and ongoing else "notable" if ongoing else "info",
            start=from_epoch(start), end=None if ongoing else from_epoch(end),
            source_url=DASHBOARD.format(code=code), source="IODA, Georgia Tech",
            tags=["internet", "outage"], data={"country_code": code, "measurements": sources,
                                              "score": max(float(r.get("score") or 0) for r in group)}))
    out.sort(key=lambda e: (e.end is not None, -e.data["score"]))
    return out[:flags.MAX_OUTAGES]


def fetch(ctx: Ctx) -> FeedResult:
    now = int(ctx.now.timestamp())
    text = ctx.get(API, {"from": now - WINDOW_S, "until": now, "entityType": "country", "limit": 200})
    events = parse(text, ctx.now)
    return FeedResult(events=events, note=f"{sum(e.end is None for e in events)} ongoing of {len(events)}")


FEED = Feed("ioda", "Internet outages", "IODA, Georgia Tech", "https://ioda.inetintel.cc.gatech.edu/", fetch)
