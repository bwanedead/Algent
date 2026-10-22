"""
Satellite watch: in-repo operator knobs (no ``.env``). Each value names its reason; cadence and caps are sized for the 4 GB server and the
imagery services' fair-use limits, not for what the data "should" look like. No threshold on the change itself lives here: that comes from
each site's own history (``change.py``).
"""

from __future__ import annotations

# ── what is watched ──────────────────────────────────────────────────────────────────────────────
#: Sites handled in one pass. Each costs about ten small requests (one STAC search, a few cloud-mask chips, one picture) at ~0.5 s pacing and a
#: couple of seconds each; 12 is a few minutes of one core. Raise it only after watching a pass's wall time on the server.
MAX_SITES_PER_PASS = 12
#: A site is looked at again no sooner than this (hours). Sentinel-2 revisits a place every 2 to 5 days; asking more often only repeats the scene.
REVISIT_HOURS = 36
#: Sites kept on the ranked watch list (a priority order; each pass takes the most overdue weighted by priority).
POOL_SIZE = 60
#: A damage statement counts toward a site's priority for this many days, fading with age (``watchlist.py``).
STRIKE_WINDOW_DAYS = 30
#: Ledger events written by the daily within this many days mean "in the developments now".
DEVELOPMENT_DAYS = 2
#: Priority weight by how firmly the damage is stated (a claim is a party's word, a confirmation someone else's).
STATUS_WEIGHT = {"claimed_struck": 1.0, "reported_damaged": 2.0, "confirmed_damaged": 3.0, "destroyed": 3.0}
#: Added when the place is in today's developments; a chokepoint zone is the floor of the list (sea scenes change little and say little).
DEVELOPMENT_BONUS = 1.5
ZONE_PRIORITY = 0.5

# ── the picture ──────────────────────────────────────────────────────────────────────────────────
CHIP_PX = 256
#: Half the side of a chip over a place, km. 2.5 km gives a 5 km square at ~20 m a pixel: a plant or depot with its yard, a port basin.
SITE_HALF_KM = 2.5
#: A zone's chip covers its box, but never more than this half-side (km): beyond it a 256 px chip is too coarse to show anything.
ZONE_HALF_KM_MAX = 25.0
#: Sentinel-2 L2A scenes searched back this many days for "latest".
LOOKBACK_DAYS = 30
#: A site with a dated strike statement gets its baseline from the scenes before that date, searched back this many days.
BASELINE_LOOKBACK_DAYS = 60
#: Scenes whose whole tile is cloudier than this are not looked at (the chip's own cloud is measured; this only skips hopeless tiles).
TILE_CLOUD_PREFILTER = 70.0
#: Candidates (newest first) whose local cloud is measured per search; the least cloudy of them wins.
CANDIDATES = 5
#: A chip with more than this share of no-data pixels (the edge of a swath) is not usable.
MAX_NODATA = 0.10

# ── judging a pair ───────────────────────────────────────────────────────────────────────────────
#: Share of pixels that must be clear in BOTH chips (not cloud, shadow, snow or no-data) for the pair to say anything. Below it: inconclusive.
MIN_VALID_SHARE = 0.60
#: A site's own observations needed before its change or its night light is judged against its own normal; fewer is "learning" and nothing is flagged.
MIN_OBS = 5

# ── night lights (NASA GIBS, VIIRS gap-filled daily) ─────────────────────────────────────────────
#: Days of lag the daily product has (the newest day the service holds is this many days back).
NIGHT_LAG_DAYS = 4
NIGHT_PX = 64
#: Half the side of the night-lights window, degrees (~11 km each way): VIIRS pixels are ~0.5 km, a plant's glow is a few pixels.
NIGHT_HALF_DEG = 0.1
