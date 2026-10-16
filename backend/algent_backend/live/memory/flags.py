"""
Live memory — in-repo operator knobs (no ``.env``). Every judgement about the data is here, with its reason, so retuning it
after a few weeks of real data is one edit. Cadences, bounds and sizes are plain engineering; thresholds are statistics.
"""

from __future__ import annotations

# ── what is observed, and how often ──────────────────────────────────────────────────────────────
#: Seconds between samples of the vessel / aircraft boards. An hour's value is the MEAN of its samples (how many were there on
#: average), so one 60 s board refresh and an adsb.lol sweep rhythm (~7 min) average out. 12 samples an hour.
SAMPLE_SECONDS = 300
#: An hour with fewer samples than this was mostly missed (the service was down or restarting): it is UNOBSERVED, not "empty".
#: A missing hour must never read as "every ship vanished" nor teach the baseline zeros.
MIN_HOUR_SAMPLES = 3
#: Places are 1-degree cells (~111 km, the same grid as the AIS receiver-coverage layer) and the named areas of ``areas.py``.
CELL_DEG = 1
#: A ship cell counts as HEARD in a sample when any vessel in it reported inside this window (AIS reports every few seconds
#: to minutes; a vessel board row older than this had no recent message).
RECENT_S = 600
#: Hours of detail kept on the server's disk (about 1-2 MB a day, see docs/guides/worker-server.md); older files are deleted.
HOUR_KEEP_DAYS = 60

# ── baselines: the learned normal, by hour of the week ───────────────────────────────────────────
#: Same-hour-of-week values remembered per place and class (ships, aircraft): the trailing six weeks. Six keeps the normal
#: current (a season, a new route) while a robust median still ignores one odd week.
BASELINE_WEEKS = 6
#: Fires have no weekly rhythm and arrive every ~3 h as a rolling 24 h picture: one slot, the last 56 observations (a week).
FIRE_DEPTH = 56
#: A slot is "learned" once it holds this many weeks (ships/aircraft) or observations (fires, 3 days of runs). Below that the
#: baseline falls back to trailing days (same hour of day, any weekday) and every anomaly it yields is marked LEARNING.
MIN_WEEKS = 3
FIRE_MIN_OBS = 24
#: The fallback needs at least this many pooled values (three days at the same hour +-1 h; fires: 8 observations) or the place
#: is simply not scored yet.
MIN_POOL = 9
FIRE_MIN_POOL = 8
#: A place that has had no activity for this many days (all remembered values zero) is forgotten, bounding the memory.
FORGET_DAYS = 21

# ── scoring: how far outside normal is far ───────────────────────────────────────────────────────
#: Robust z = (value - median) / sigma, sigma = max(1.4826 * MAD, POISSON_SHARE * sqrt(median), 1). 1.4826 makes MAD comparable to a
#: standard deviation for bell-shaped noise. The square-root floor is the spread of a COUNT (a place that usually holds 16 ships swings
#: by a few for no reason) so a few identical weeks (MAD 0) never make the spread zero; it is halved because an hour's value is the mean of
#: twelve samples of objects that stay for hours, so it varies far less than independent arrivals would. The floor of 1 means a change of
#: fewer than one object never counts.
POISSON_SHARE = 0.5
Z_ENTER = 3.5          # Iglewicz and Hoaglin's standard cut for a modified z-score outlier
Z_EXIT = 2.0           # hysteresis: a flagged run goes on until the score falls back under 2 (or flips sign)
#: A run is only PUBLISHED once it has stayed flagged this many consecutive observations (hours; fires: runs). One odd hour
#: is noise; three in a row is something. Fires arrive ~3-hourly so two runs (6 h) is the same evidence.
PERSIST_HOURS = 3
FIRE_PERSIST_OBS = 2
#: A run is closed when no observation arrived for this many hours (the source went quiet; its state is unknown).
MAX_GAP_HOURS = 6
#: A learning baseline (not yet a full set of weeks) must clear a higher bar before anything is published.
LEARNING_Z = 6.0
#: "Fewer than normal" is only believable when normal was at least this many objects (you cannot fall from 1 to 0 in a way
#: that means anything), and the rest of the place's traffic - the receiver-alive evidence - must also be at least this big.
MIN_LOW_NORMAL = 3.0
MIN_COMPANION = 3.0
#: Values enter the baseline unless they belong to a run opened less than this long ago: an incident must not teach the
#: baseline that it is normal, but a lasting change (a new route, a closed port) becomes the new normal after three days.
FREEZE_HOURS = 72

# ── coverage-gap suppression: "no receiver" is not "no ships" ───────────────────────────────────
#: A "below normal" is dropped when the rest of the place's traffic fell too (score <= -Z_EXIT: the place went quiet as a
#: whole, which is a receiver or feed gap), when the place's receiver coverage (share of its 24 h-covered cells heard inside
#: RECENT_S, hour mean) is under HEARD_SHARE, or when the whole WORLD layer is itself low (a feed outage).
HEARD_SHARE = 0.5

# ── what is shown ────────────────────────────────────────────────────────────────────────────────
#: Cells of one series, one direction, within this many degrees of a stronger flagged cell merge into it (one event, not nine).
CLUSTER_DEG = 2.0
#: At most this many anomalies are published (strongest first): a reader budget, not a judgement.
MAX_PUBLISHED = 40
#: Closed anomalies stay in the site's table this many days.
RETAIN_DAYS = 14
#: Evidence lines a section writer sees for one theater / for the sweep.
DESK_LINES = 6
SWEEP_LINES = 8

# ── daily rollups ────────────────────────────────────────────────────────────────────────────────
#: A UTC day becomes a ``live_mem_*`` observation only with at least this many observed hours; fewer is a service outage, not a quiet day.
DAY_MIN_HOURS = 18
