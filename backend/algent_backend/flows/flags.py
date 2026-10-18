"""
Flows — in-repo operator knobs (no ``.env``). Cadences and bounds are plain engineering; the few judgements about the data are
named here with their reason so retuning them after a few weeks of real data is one edit.
"""

from __future__ import annotations

# ── the lane tracker (inside the stream service) ─────────────────────────────────────────────────
#: Seconds between tracker passes over the vessel board. A ship moves ~2 km in this time and the smallest place box is ~40 km wide,
#: so no passage is missed; the pass is ~60 000 grid lookups (well under a second).
CYCLE_SECONDS = 300
#: Seconds between saves of the tracker's state to disk (a restart then loses at most this much; the live board refills in minutes).
PERSIST_SECONDS = 900
#: A vessel's last place is forgotten after this many days unseen (it starts fresh), and the memory never holds more than STATE_MAX.
STATE_KEEP_DAYS = 14
STATE_MAX = 200000
#: A hop (last place -> this place) is only believed when it took no longer than this. A ship dark for longer than a voyage between
#: neighbouring regions is a different trip; counting it would invent a lane crossing.
HOP_MAX_DAYS = 21
#: No merchant ship steers faster than ~27 knots; a hop that would need more (km of lane route over elapsed hours) is a spoofed or
#: re-used identity and is dropped. 50 km/h = 27 kn.
MAX_SPEED_KMH = 50.0
#: Leaving a place and coming straight back inside this window (a ship idling on a box edge, an anchorage on the boundary) is one
#: visit, not a hop out and a hop back.
FLICKER_S = 6 * 3600
#: Days of daily aggregates kept (the 30-day rate and the anomaly's normal need ~40; older days are dropped).
DAY_KEEP = 90
#: Directed-lane hop durations kept as the short sample behind a lane's typical transit time.
HOP_SAMPLES = 8

# ── rates and anomaly ────────────────────────────────────────────────────────────────────────────
#: Rolling windows of the published rates (days).
WINDOWS = (7, 30)
#: A place's latest COMPLETE day is judged against its earlier days only when it has at least this many of them (a normal learned
#: from fewer is not a normal), counting only days the tracker watched for most of the day.
ANOMALY_MIN_DAYS = 7
#: A day counts as watched when the tracker cycled for at least this share of it.
WATCHED_SHARE = 0.75
#: The anomaly score is the live memory's robust modified z (live/memory/robust.py) against the place's earlier days, judged with
#: the same cut as the rest of /live (live/memory/flags.Z_ENTER).

# ── trade (commodity and money flows) ────────────────────────────────────────────────────────────
#: Days a fetched trade picture is reused before the next refresh. Annual statistics change a few times a year.
TRADE_REFRESH_DAYS = 7
#: Seconds to wait between calls to the Comtrade public preview API (rate limited; keyless).
COMTRADE_GAP_S = 1.5
#: Partner flows kept per exporter and commodity / per exporter of money, strongest first. A reader budget (a screen of arcs), not a
#: judgement about trade.
GRAIN_TOP_PARTNERS = 5
MONEY_TOP_PARTNERS = 4
#: How many recent years to try, newest first, for an exporter that has not yet filed the latest (reporters file with a lag of months
#: to years; a few file nothing at all).
TRADE_YEARS_BACK = 3
