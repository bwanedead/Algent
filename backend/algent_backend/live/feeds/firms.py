"""
NASA FIRMS — VIIRS thermal hotspots in the watched boxes (``regions.FIRE_BOXES``). Needs a free MAP_KEY
(``ALGENT_FIRMS_KEY``, https://firms.modaps.eosdis.nasa.gov/api/map_key/); without it the feed reports so cleanly.

Per box: hotspots of the last day (VIIRS S-NPP near-real-time), low-confidence ones dropped, merged into one event per
~11 km cell (count, strongest fire radiative power), at most ``MAX_FIRES_PER_BOX`` biggest per box. Stat: hotspots
per box per day. A hotspot is a satellite heat reading; wildfire, an industrial flare or a strike all show up.
"""

from __future__ import annotations

import csv
import io
from collections import defaultdict

from algent_backend.instruments.live_series import fire_id

from .. import flags
from ..contracts import Ctx, Feed, FeedResult, LiveEvent, NeedsKey, Stat
from ..regions import FIRE_BOXES

URL = "https://firms.modaps.eosdis.nasa.gov/api/area/csv/{key}/VIIRS_SNPP_NRT/{w},{s},{e},{n}/1"
SIGNUP = "https://firms.modaps.eosdis.nasa.gov/api/map_key/"
PAGE = "https://firms.modaps.eosdis.nasa.gov/map/"


def parse(text: str, box) -> tuple[list[LiveEvent], int]:
    rows = [r for r in csv.DictReader(io.StringIO(text)) if r.get("latitude") and (r.get("confidence") or "n").lower() in flags.FIRE_CONFIDENCE]
    cells: dict[tuple[int, int], list[dict]] = defaultdict(list)
    for r in rows:
        cells[(int(float(r["latitude"]) // flags.FIRE_CELL_DEG), int(float(r["longitude"]) // flags.FIRE_CELL_DEG))].append(r)
    ranked = sorted(cells.items(), key=lambda kv: -sum(float(x.get("frp") or 0) for x in kv[1]))[:flags.MAX_FIRES_PER_BOX]
    events = []
    for (cy, cx), pts in ranked:
        frp = max(float(x.get("frp") or 0) for x in pts)
        date, time = pts[0].get("acq_date", ""), (pts[0].get("acq_time") or "0000").zfill(4)
        events.append(LiveEvent(
            id=f"firms:{box.slug}:{cy}:{cx}", feed="firms", kind="fire", countries=list(box.countries), tags=list(box.tags),
            lat=round((cy + 0.5) * flags.FIRE_CELL_DEG, 3), lon=round((cx + 0.5) * flags.FIRE_CELL_DEG, 3),
            title=f"Satellite heat hotspot{'s' if len(pts) > 1 else ''} near {box.label}",
            detail=(f"{len(pts)} VIIRS satellite heat reading{'s' if len(pts) > 1 else ''} in a ~11 km cell in the last day "
                    f"(strongest {frp:.0f} MW). That can be a wildfire, an industrial flare or a strike; the satellite cannot tell which."),
            severity="info", start=f"{date}T{time[:2]}:{time[2:]}:00+00:00" if date else "", source_url=PAGE,
            source="NASA FIRMS (VIIRS)", data={"box": box.slug, "hotspots": len(pts), "frp_mw": frp}))
    return events, len(rows)


def fetch(ctx: Ctx) -> FeedResult:
    if not ctx.key:
        raise NeedsKey(FEED.needs())
    events, stats = [], []
    for b in FIRE_BOXES:
        s, w, n, e = b.box
        got, count = parse(ctx.get(URL.format(key=ctx.key, w=w, s=s, e=e, n=n)), b)
        events += got
        stats.append(Stat(series_id=fire_id(b.slug), value=count))
    return FeedResult(events=events, stats=stats, note=f"{len(events)} hotspot cells in {len(FIRE_BOXES)} boxes")


FEED = Feed("firms", "Fire hotspots", "NASA FIRMS", PAGE, fetch, key_env="ALGENT_FIRMS_KEY", signup_url=SIGNUP)
