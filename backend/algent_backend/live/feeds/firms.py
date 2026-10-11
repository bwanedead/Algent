"""
NASA FIRMS — VIIRS thermal hotspots for the WHOLE WORLD, last 24 h (VIIRS S-NPP near-real-time). Needs a free MAP_KEY
(``ALGENT_FIRMS_KEY``, https://firms.modaps.eosdis.nasa.gov/api/map_key/); without it the feed reports so cleanly.

One pass over the detections, three products:
  * the HEAT document (``fires``): every detection folded into 0.25 degree cells (count + strongest FRP), which the
    site's map draws as a heat layer that resolves into dots when zoomed in (``fire_grid.py``);
  * NOTABLE events: the day's extreme cells (intensity or concentration, relative to the day), one event per blaze;
  * the WATCHED boxes (``regions.FIRE_BOXES``: front lines, refinery belts) keep their ``live_fire_*`` day series and
    their finer 0.1 degree cell events.
The planet is fetched as 8 tiles of 90 degrees (flags.FIRE_TILE_DEG), streamed line by line; memory holds only the cells.
Low-confidence detections are dropped. A hotspot is a satellite heat reading; a wildfire, an industrial flare or a
strike all show up, and the data alone does not say which.

KEY LIMIT: FIRMS allows 5000 transactions per 10 minutes per MAP_KEY. One run is 8 area requests + 1 status check, every
3 hours: 72 requests a day, orders of magnitude inside it. The status endpoint is read first and the run is skipped if
the key is already near its limit.
"""

from __future__ import annotations

import csv
import json
from collections import defaultdict
from typing import Iterator

from algent_backend.instruments.live_series import fire_id

from .. import flags, places
from ..contracts import Ctx, Feed, FeedResult, LiveEvent, NeedsKey, Stat, iso
from ..fire_grid import Cell, FireGrid, notable
from ..regions import FIRE_BOXES, inside

URL = "https://firms.modaps.eosdis.nasa.gov/api/area/csv/{key}/VIIRS_SNPP_NRT/{w},{s},{e},{n}/1"
STATUS = "https://firms.modaps.eosdis.nasa.gov/mapserver/mapkey_status/?MAP_KEY={key}"
SIGNUP = "https://firms.modaps.eosdis.nasa.gov/api/map_key/"
PAGE = "https://firms.modaps.eosdis.nasa.gov/map/"


def tiles() -> list[tuple[int, int, int, int]]:
    """(west, south, east, north) of every tile covering the planet."""
    t = flags.FIRE_TILE_DEG
    return [(w, s, w + t, s + t) for s in range(-90, 90, t) for w in range(-180, 180, t)]


def quota_left(ctx: Ctx) -> bool:
    """False only when FIRMS itself says this key cannot afford another run's requests; any doubt means go."""
    try:
        doc = json.loads(ctx.get(STATUS.format(key=ctx.key)))
        return float(doc["current_transactions"]) + len(tiles()) <= float(doc["transaction_limit"])
    except Exception:  # noqa: BLE001 - the status check is a courtesy, never a gate on its own failure
        return True


def _stamp(row: dict) -> int:
    date, time = (row.get("acq_date") or "").replace("-", ""), (row.get("acq_time") or "0000").zfill(4)
    return int(date + time) if date.isdigit() and time.isdigit() else 0


class Tally:
    """Everything one run learns, folded as detections stream by."""

    def __init__(self) -> None:
        self.world = FireGrid()
        self.box_cells: dict[str, dict[tuple[int, int], list]] = {b.slug: defaultdict(list) for b in FIRE_BOXES}
        self.box_count: dict[str, int] = {b.slug: 0 for b in FIRE_BOXES}

    def add_rows(self, lines: Iterator[str]) -> int:
        n = 0
        for r in csv.DictReader(lines):
            if not r.get("latitude") or (r.get("confidence") or "n").lower() not in flags.FIRE_CONFIDENCE:
                continue
            try:
                lat, lon, frp = float(r["latitude"]), float(r["longitude"]), float(r.get("frp") or 0)
            except ValueError:
                continue
            stamp = _stamp(r)
            self.world.add(lat, lon, frp, stamp)
            n += 1
            for b in FIRE_BOXES:
                if inside(b.box, lat, lon):
                    self.box_count[b.slug] += 1
                    self.box_cells[b.slug][(int(lat // flags.FIRE_CELL_DEG), int(lon // flags.FIRE_CELL_DEG))].append((frp, stamp))
        return n


def _start(stamp: int) -> str:
    s = f"{stamp:012d}"
    return f"{s[:4]}-{s[4:6]}-{s[6:8]}T{s[8:10]}:{s[10:12]}:00+00:00" if stamp else ""


def box_events(tally: Tally) -> list[LiveEvent]:
    events = []
    for b in FIRE_BOXES:
        ranked = sorted(tally.box_cells[b.slug].items(), key=lambda kv: -sum(f for f, _ in kv[1]))[:flags.MAX_FIRES_PER_BOX]
        for (cy, cx), pts in ranked:
            frp = max(f for f, _ in pts)
            events.append(LiveEvent(
                id=f"firms:{b.slug}:{cy}:{cx}", feed="firms", kind="fire", countries=list(b.countries), tags=list(b.tags),
                lat=round((cy + 0.5) * flags.FIRE_CELL_DEG, 3), lon=round((cx + 0.5) * flags.FIRE_CELL_DEG, 3),
                title=f"Satellite heat hotspot{'s' if len(pts) > 1 else ''} near {b.label}",
                detail=(f"{len(pts)} VIIRS satellite heat reading{'s' if len(pts) > 1 else ''} in a ~11 km cell in the last day "
                        f"(strongest {frp:.0f} MW). That can be a wildfire, an industrial flare or a strike; the satellite cannot tell which."),
                severity="info", start=_start(max(s for _, s in pts)), source_url=PAGE, source="NASA FIRMS (VIIRS)",
                data={"box": b.slug, "hotspots": len(pts), "frp_mw": frp}))
    return events


def notable_events(cells: list[Cell]) -> list[LiveEvent]:
    watched = lambda lat, lon: any(inside(b.box, lat, lon) for b in FIRE_BOXES)   # noqa: E731 - the box events cover those
    out = []
    for c in notable(cells, skip=watched):
        country = places.country_at(c.lat, c.lon)
        where = f"in {country}" if country else "offshore or outside any mapped country"
        out.append(LiveEvent(
            id=f"firms:notable:{round(c.lat / flags.FIRE_GRID_DEG)}:{round(c.lon / flags.FIRE_GRID_DEG)}", feed="firms", kind="fire",
            lat=c.lat, lon=c.lon, countries=[country] if country else [], tags=["fires", "notable"], severity="notable",
            title=f"Strong satellite heat reading {where}",
            detail=(f"{c.n} VIIRS heat reading{'s' if c.n > 1 else ''} in a ~27 km cell in the last day, the strongest {c.frp:.0f} MW: among the "
                    "day's most intense or most concentrated anywhere. That can be a large wildfire, an industrial flare or a strike; "
                    "the satellite cannot tell which."),
            start=_start(c.last), source_url=PAGE, source="NASA FIRMS (VIIRS)",
            data={"hotspots": c.n, "frp_mw": c.frp, "notable": True}))
    return out


def fetch(ctx: Ctx) -> FeedResult:
    if not ctx.key:
        raise NeedsKey(FEED.needs())
    if not quota_left(ctx):
        raise RuntimeError("FIRMS transaction limit nearly reached for this key; skipping this run")
    tally, grid = Tally(), None
    for w, s, e, n in tiles():
        url = URL.format(key=ctx.key, w=w, s=s, e=e, n=n)
        tally.add_rows(iter(ctx.lines(url)) if ctx.lines else iter(ctx.get(url).splitlines()))
    grid = tally.world
    events = box_events(tally) + notable_events(grid.rows())
    stats = [Stat(series_id=fire_id(b.slug), value=tally.box_count[b.slug]) for b in FIRE_BOXES]
    return FeedResult(events=events, stats=stats, docs={"fires": grid.doc(iso(ctx.now))},
                      note=f"{grid.total} detections worldwide in {len(grid.cells)} cells, {sum(e.data.get('notable', False) for e in events)} notable")


FEED = Feed("firms", "Fire hotspots", "NASA FIRMS", PAGE, fetch, key_env="ALGENT_FIRMS_KEY", signup_url=SIGNUP)
