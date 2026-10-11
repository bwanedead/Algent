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
