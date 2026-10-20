"""
GNSS interference - in-repo operator knobs (no ``.env``). Each judgement has its reason; retune after a few weeks of real data.
"""

from __future__ import annotations

#: NACp (Navigation Accuracy Category - position) below this counts as degraded. NACp 8-11 is the normal range for a modern airliner
#: (under 0.05 nautical miles); 7 is under 0.1 nm; below 7 means the aircraft itself no longer trusts its position to a tenth of a mile.
#: Only ADS-B version 2 transponders report it (version 0/1 carry no usable NACp), and only ADS-B-sourced positions count (not MLAT, whose
#: NIC is always 0 because the position is computed on the ground).
DEGRADED_NACP = 7

#: Cells are one degree square (~111 km, the same grid as live memory's cells): wide enough to hold a few dozen aircraft a day, narrow enough
#: that a Kaliningrad-sized zone does not smear across a country.
CELL_DEG = 1.0

#: A day-cell needs this many aircraft observations (the sum over the hourly samples) before it is scored: a share of 2 out of 3 aircraft is not a zone.
MIN_OBSERVATIONS = 12
#: Below this share of degraded observations a cell is background (a few old or faulty avionics are always there). 2% is also GPSJam's
#: own lowest published band, so the two sources use the same floor.
MIN_SHARE = 0.02
#: ...and at least this many degraded observations: one aircraft with faulty avionics, seen in a few samples, is not a zone.
MIN_DEGRADED = 3
#: Severity bands by share of degraded observations. High means about a third of the aircraft lost trustworthy positioning; GPSJam's top band
#: starts at 10%, ours is split into medium (10-30%) and high so a strongly jammed area stands out from a mildly affected one.
MEDIUM_SHARE = 0.10
HIGH_SHARE = 0.30

#: Flags need history: the first week is only baseline. A cell is "new" when it was observed on at least MIN_CELL_DAYS earlier days, none of them
#: elevated (its median share under MIN_SHARE), and today it reaches ENTER_SHARE. It is "intensifying" when its normal was already elevated and
#: today's share is a robust outlier of its own history (live memory's modified z-score, Z_ENTER) and at least ENTER_SHARE.
FLAG_AFTER_DAYS = 7
MIN_CELL_DAYS = 3
HISTORY_DAYS = 28
ENTER_SHARE = 0.05

#: Hourly sample points: (name, latitude, longitude). Each is a 250 nm (the API maximum) radius around the point on adsb.lol. The list is the known
#: interference regions plus control areas where we expect nothing; a control showing a rise is a sign the method, not the sky, is moving.
RADIUS_NM = 250
PROBES: tuple[tuple[str, float, float], ...] = (
    ("Baltic / Kaliningrad", 55.0, 20.5), ("Gulf of Finland", 59.5, 26.0), ("Lithuania / Belarus border", 54.5, 25.5), ("Poland east", 52.0, 22.0),
    ("Black Sea west", 44.0, 28.5), ("Crimea / Black Sea", 44.5, 34.0), ("Ukraine east / Russia border", 49.5, 37.0), ("Caucasus", 41.5, 44.5),
    ("Turkey south-east / Syria / Iraq", 36.5, 40.0), ("Eastern Mediterranean", 34.0, 34.5), ("Israel / Jordan / Sinai", 31.0, 35.0),
    ("Persian Gulf", 26.5, 52.0), ("Strait of Hormuz / Gulf of Oman", 25.5, 57.0), ("Red Sea / Yemen", 15.0, 43.0), ("Northern Iran / Caspian", 37.0, 50.0),
    ("Afghanistan / Pakistan", 33.0, 69.0), ("India / Pakistan", 30.0, 73.0), ("Myanmar", 20.0, 96.0), ("Korean peninsula", 37.5, 127.5),
    ("Taiwan Strait", 24.5, 120.0), ("South China Sea", 16.0, 113.0), ("Libya / Egypt", 30.5, 25.0), ("Norway / Kola", 69.0, 28.0),
    ("Control: western Europe", 50.0, 5.0), ("Control: eastern US", 39.5, -76.0), ("Control: western US", 34.0, -118.0), ("Control: south-east Australia", -33.8, 151.0),
)

#: GPSJam publishes one CSV a day (``hex, count_good_aircraft, count_bad_aircraft``) on an H3 resolution-4 grid (~22 km edge). Cells under
#: MIN_SHARE are background; the site database gets only cells at GPSJAM_PUBLISH_SHARE or above (GPSJam's own top band) to bound its size.
GPSJAM_URL = "https://gpsjam.org/data/{day}-h3_4.csv"
GPSJAM_MIN_AIRCRAFT = 8
GPSJAM_PUBLISH_SHARE = 0.10
GPSJAM_EDGE_DEG = 0.25
#: The file for day D appears on D+1 (or later): try these many days back from yesterday.
GPSJAM_LOOKBACK = 3

#: Reader window and doctor staleness.
PUBLISH_DAYS = 30
STALE_HOURS = 3
DESK_LINES = 6
RETRIEVAL_DAYS = 21
