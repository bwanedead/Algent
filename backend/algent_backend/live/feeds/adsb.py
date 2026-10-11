"""
Military aircraft — adsb.lol ``/v2/mil`` (keyless): every military-flagged aircraft currently broadcasting ADS-B.

One call per run. Per watched region we count aircraft in the box and by role (tanker, surveillance, airlift, other;
type codes in ``regions.py``). Stats are the region's day maximum (aircraft in the air at once) and the same for
tankers plus surveillance aircraft ("support" flights, the ones that precede or enable operations). Events are one
cluster per region that has any aircraft, at the aircraft's centre; individual tail numbers are never published.

HONEST LIMIT: this is only aircraft that broadcast ADS-B and that volunteer receivers hear. Many military flights
fly with transponders off. A count is a floor, and a change in it can be coverage, not activity.
"""

from __future__ import annotations

import json
import statistics

from algent_backend.instruments import store as istore
from algent_backend.instruments.live_series import mil_ids

from ..contracts import Ctx, Feed, FeedResult, LiveEvent, Stat, iso
from ..regions import REGIONS, inside, role_of

URL = "https://api.adsb.lol/v2/mil"
PAGE = "https://adsb.lol/"
USUAL_DAYS = 14                    # the recent days "usually" is judged over


def _usual(series_id: str) -> float | None:
    vals = [o.value for o in istore.history(series_id)[-USUAL_DAYS:]]
    return statistics.median(vals) if len(vals) >= 5 else None


def parse(text: str, ctx: Ctx) -> FeedResult:
    planes = [a for a in json.loads(text).get("ac", []) if isinstance(a.get("lat"), (int, float)) and isinstance(a.get("lon"), (int, float))]
    events, stats = [], []
    for r in REGIONS:
        here = [a for a in planes if inside(r.box, a["lat"], a["lon"])]
        roles = [role_of(a.get("t", "")) for a in here]
        n_support = sum(x in ("tanker", "surveillance") for x in roles)
        total_id, support_id = mil_ids(r.slug)
        stats += [Stat(series_id=total_id, value=len(here)), Stat(series_id=support_id, value=n_support)]
        if not here:
            continue
        counts = {k: roles.count(k) for k in ("tanker", "surveillance", "airlift", "other") if roles.count(k)}
        usual = _usual(total_id)
        parts = [f"{v} {k}" for k, v in counts.items()]
        normal = f" That is {'above' if len(here) > usual else 'below' if len(here) < usual else 'about'} the usual {usual:.0f} " \
                 f"(median daily peak, last {USUAL_DAYS} days)." if usual is not None else ""
        events.append(LiveEvent(
            id=f"adsb:{r.slug}", feed="adsb", kind="aircraft", countries=list(r.countries), tags=list(r.tags),
            lat=round(sum(a["lat"] for a in here) / len(here), 3), lon=round(sum(a["lon"] for a in here) / len(here), 3),
            title=f"{len(here)} military aircraft over the {r.label}",
            detail=(f"{len(here)} military-flagged aircraft are broadcasting a position in this area right now ({', '.join(parts)})."
                    f"{normal} Only aircraft that broadcast ADS-B and are heard by volunteer receivers appear; many military "
                    "flights fly without it, so this is a minimum."),
            severity="info", start=iso(ctx.now), source_url=PAGE, source="adsb.lol",
            data={"region": r.slug, "count": len(here), "roles": counts, "usual": usual}))
    return FeedResult(events=events, stats=stats, note=f"{len(planes)} aircraft worldwide, {len(events)} regions occupied")


def fetch(ctx: Ctx) -> FeedResult:
    return parse(ctx.get(URL), ctx)


FEED = Feed("adsb", "Military aircraft", "adsb.lol", PAGE, fetch)
