"""
Live feeds — in-repo operator knobs (no ``.env``; credentials stay in the environment, see docs/credentials.md).

Every number here is a cadence, a reader budget or a scientific fact, not a judgement about the data.
"""

from __future__ import annotations

#: Minutes between runs of each timer feed (`newsroom live schedule` prints these; infra/server/install_schedules.sh
#: turns them into systemd timers). Chosen from how often each SOURCE actually changes, and to stay polite:
#: IODA recomputes every ~5 min; USGS updates its summary feeds every minute but quakes are rare; adsb.lol is a
#: live picture, a quarter-hour gives a fair daily maximum; FIRMS VIIRS passes land a few times a day.
CADENCE_MINUTES: dict[str, int] = {"ioda": 15, "usgs": 10, "adsb": 15, "firms": 180}

#: Seconds an IODA outage may have ended before "now" and still count as ongoing. IODA's own detection runs on
#: 5-minute bins, so one missed bin is not the end of an outage.
OUTAGE_END_SLACK_S = 900

#: USGS calls an earthquake "major" from magnitude 7.0 (USGS: "major: 7.0-7.9"). A fact about the scale, not
#: our threshold.
MAJOR_MAGNITUDE = 7.0

#: USGS summary feed to read: `4.5_day` = every quake M4.5+ in the past day (USGS lists many other windows).
QUAKE_FEED = "4.5_day"

#: Reader budgets (every event is a dot and a popover; more than this is clutter, not information).
MAX_OUTAGES = 40
MAX_FIRES_PER_BOX = 12

#: FIRMS hotspot clusters merge into one dot per grid cell this many degrees wide (~11 km).
FIRE_CELL_DEG = 0.1
#: VIIRS confidence classes kept: l(ow) is dropped, n(ominal) and h(igh) stay (FIRMS user guide).
FIRE_CONFIDENCE = ("n", "h")

#: Days of a series' history pushed to the site's live_stats table (tiles compare today with the recent normal).
PUBLISH_STATS_DAYS = 45

#: AIS: seconds between the running counter's flushes of its day counts to the store, and how long a vessel's
#: last side of a gate line is remembered (a ship not seen again within this many seconds starts fresh, so a
#: ship that anchors for a day and drifts across is not counted by a stale position).
AIS_FLUSH_SECONDS = 300
AIS_TRACK_TTL_S = 6 * 3600
AIS_RECONNECT_MAX_S = 300

#: Energy tiles on /live (series id, label). Yahoo-backed prices are delayed and the catalog keeps them off public display by
#: default; listing them here is the operator's decision to show them. Delete a line to take a tile off the page.
ENERGY_TILES: tuple[tuple[str, str], ...] = (("px_brent", "Brent crude"), ("px_wti", "WTI crude"),
                                             ("px_ttf_gas", "TTF gas, Europe"), ("px_henry_gas", "Henry Hub gas, US"))

#: Items on the "What's happening now" strip.
HEADLINES_MAX = 6

# ── world fires (FIRMS) ───────────────────────────────────────────────────────────────────────
#: The world is fetched as tiles this many degrees square (8 requests, each ~1/8 of the planet: a smaller body each, so a
#: slow link or a big fire season never means one 40 MB download). Tile edges are multiples of the grid below.
FIRE_TILE_DEG = 90
#: Every detection is folded into a grid cell this wide (~27 km); the heat layer gets count + strongest FRP per cell.
FIRE_GRID_DEG = 0.25
#: Cells published (strongest first). The cap is the payload bound, not a judgement about fires.
FIRE_MAX_CELLS = 30000
#: A cell is NOTABLE when its strongest reading, or its detection count, is in the top 0.1% of that day's cells
#: (relative to the day, so a savanna-burning season does not flood the list), at most MAX_NOTABLE_FIRES, no two within
#: NOTABLE_SEPARATION_DEG of each other (one blaze is one event).
NOTABLE_QUANTILE = 0.999
MAX_NOTABLE_FIRES = 12
NOTABLE_SEPARATION_DEG = 1.5

# ── ships and aircraft: live positions ────────────────────────────────────────────────────────
#: aisstream bounding boxes ((south, west), (north, east)). The whole world by default; if the stream proves too heavy
#: for the server, list several large sea-lane boxes here instead (the position board and gate counter don't care).
AIS_BOXES: tuple[tuple[tuple[float, float], tuple[float, float]], ...] = (((-90.0, -180.0), (90.0, 180.0)),)
#: A vessel not heard for this long leaves the board; the board never holds more than AIS_MAX_VESSELS (freshest kept).
AIS_VESSEL_TTL_S = 1800
AIS_MAX_VESSELS = 12000
#: Seconds between published snapshots (vessels.json / aircraft.json / summary.json) and between track-shard publishes.
SNAPSHOT_SECONDS = 60
TRACK_SECONDS = 300
#: Short trails: at most TRACK_POINTS per object, a point at most every TRACK_STEP_S, nothing older than TRACK_KEEP_S.
TRACK_POINTS = 24
TRACK_STEP_S = 300
TRACK_KEEP_S = 7200
TRACK_SHARDS = 16
#: Civil aircraft come from adsb.lol area queries (its API has no worldwide dump): each cycle polls the next
#: CIVIL_POLLS_PER_CYCLE hubs of regions.CIVIL_HUBS, so the planet is swept every few minutes at a polite rate.
CIVIL_POLLS_PER_CYCLE = 3
CIVIL_TTL_S = 480
MIL_TTL_S = 240
AIRCRAFT_MAX = 8000
#: Snapshot objects in the public Storage bucket carry this cache header (the site polls every minute).
SNAPSHOT_CACHE = "public, max-age=20"
#: A ship is "dark" when it was last heard moving this long ago while the board still holds it (it leaves at AIS_VESSEL_TTL_S).
DARK_AFTER_S = 900
