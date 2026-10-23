"""
Maritime behaviour — in-repo operator knobs (no ``.env``). Every judgement about the data is here, with its reason, so retuning after a few
weeks of real traffic is one edit. Bounds and cadences are plain engineering; the rest are judgements, and each detector also writes the
numbers it used into the event (``detail``) and a one-sentence ``rationale``, so a reader sees why it fired.
"""

from __future__ import annotations

# ── memory: what is kept per vessel ──────────────────────────────────────────────────────────────
#: A vessel's profile expires this long after it was last heard (a ship that never comes back is forgotten); the book never holds
#: more than ``PROFILE_MAX`` (freshest kept). Budget: ~0.5 KB a vessel (a stationary ship keeps ONE sample, a mover up to
#: ``SAMPLES_MAX``), so 50 000 vessels are a few tens of MB of the 4 GB server.
PROFILE_KEEP_S = 4 * 86400
PROFILE_MAX = 50000
#: One position sample per vessel at most this often (hourly: a ship covers ~15 nm in an hour, enough to see where it went), capped
#: per vessel. A ship that has not moved ``STILL_M`` since its last sample overwrites it instead of adding one.
SAMPLE_STEP_S = 3600
SAMPLES_MAX = 96
STILL_M = 300
#: Identity changes remembered per vessel (name, IMO, ship type), newest kept.
CHANGES_MAX = 12
#: Seconds between two persists of the profile book (gzip JSON; the loop thread builds the document, a worker thread writes it).
PERSIST_SECONDS = 900
#: Seconds between two detector passes (STS and loitering need the live board; gaps need only the profiles).
DETECT_SECONDS = 300
#: Hours of area activity (hourly samples per 1-degree cell) kept for judging whether a place went silent.
ACTIVITY_KEEP_H = 4 * 24

# ── events ───────────────────────────────────────────────────────────────────────────────────────
#: Events stay in the current picture (and the site table) this many days after they end; the long record is the append-only log.
RETAIN_DAYS = 30
#: At most this many events are kept in the current picture (newest first): a storage / reader bound.
EVENTS_MAX = 3000
#: A still-going event is re-sent to the site table at most this often when only its moving parts changed (last heard, evidence, detail
#: numbers): the site shows the event's state and words, which are in the table at once whenever they change. Six hours keeps the
#: "last seen" on the page honest while cutting ~70 rewrites a day per ongoing event to 4.
PUBLISH_REFRESH_H = 6
#: Points of evidence kept on one event.
EVIDENCE_POINTS = 24

# ── names ────────────────────────────────────────────────────────────────────────────────────────
#: Two names are "the same" when one is a prefix of the other (AIS truncates at 20 / 24 characters and Class B drops suffixes) or their
#: character similarity is at least this (difflib ratio): one mistyped letter in a 10-letter name scores ~0.9, a rename scores < 0.6.
NAME_SAME_RATIO = 0.75
#: Names shorter than this (after folding) are not compared: "A", "X1" and placeholder strings are noise, not identities.
NAME_MIN_CHARS = 4

# ── 1. AIS gap ("went dark") ─────────────────────────────────────────────────────────────────────
#: A vessel silent this long is a gap candidate. Six hours is longer than any coastal blind spot a vessel crosses inside busy shipping
#: lanes, and shorter than a voyage leg, so a silence this long INSIDE heard water is the signal.
GAP_MIN_S = 6 * 3600
#: It must have been underway when last heard (a ship that stopped, then went quiet, arrived or powered down at berth).
GAP_LAST_MIN_KN = 2.0
#: "Heard water": the 3 x 3 block of 1-degree cells around the last position. Before the silence it must have held at least
#: ``GAP_MIN_BEFORE`` hourly samples an hour from OTHER vessels (a lane, not empty ocean); during the silence it must have kept at least
#: ``GAP_ALIVE_SHARE`` of that rate (neighbours were still heard, so receivers were alive). A place that went quiet as a whole is a
#: receiver gap, not a dark ship.
GAP_NEIGHBOUR_DEG = 1
GAP_MIN_BEFORE = 2.0
GAP_ALIVE_SHARE = 0.5
#: The hours compared: before = the ``GAP_BASE_H`` hours up to the last report; during = from one hour after it to now.
GAP_BASE_H = 6
#: The receivers must be alive NOW: the block held an AIS position heard within this many seconds.
GAP_NOW_HEARD_S = 3600
#: A vessel that reappears at least this far from its last position went on moving while dark; nearer, it went quiet in place (a
#: transponder switched off while drifting or at anchor).
GAP_MOVED_KM = 30.0
#: Confidence saturates with gap length (twice the minimum is full marks); a tanker weighs more (the dark-fleet question is about oil).
GAP_FULL_S = 2 * GAP_MIN_S
#: A gap whose vessel never came back is closed (unresolved) after this long without a position (the profile has expired by then).
GAP_UNRESOLVED_S = 3 * 86400

# ── 2. ship-to-ship (STS) transfer candidates ────────────────────────────────────────────────────
#: Both vessels this slow (knots) and this close (metres) for ``STS_MIN_S`` seconds. Hull-to-hull transfers happen alongside, with
#: fenders, at near-zero speed; hundreds of metres leaves room for AIS position error and a vessel swinging at anchor.
STS_MAX_KN = 1.5
STS_MAX_M = 500
STS_MIN_S = 2 * 3600
#: Positions fresher than this are "now" (a vessel not heard within it is not part of this pass); an encounter is closed when no
#: pass saw the pair for ``STS_LOST_S``.
FRESH_S = 900
STS_LOST_S = 1800
#: Partner ship types: tanker, cargo or unknown-type (AIS 70-89, 0). A pair needs at least one tanker (80-89). Tugs, pilots, fishing,
#: military and passenger craft sit close to ships for ordinary reasons.
STS_PARTNER_TYPES = (0, *range(70, 90))
#: An anchorage is not an STS: when at least ``CROWD_N`` OTHER slow vessels lie within ``CROWD_KM`` of the pair, the pair is among a
#: waiting crowd and is dropped. A pair together longer than ``STS_LAYUP_H`` hours is a lay-up pair more than a transfer
#: (its confidence is halved).
CROWD_KM = 5.0
CROWD_N = 6
STS_LAYUP_H = 36
#: Confidence saturates with the encounter length (four times the minimum is full marks).
STS_FULL_S = 4 * STS_MIN_S

# ── port / anchorage exclusion ───────────────────────────────────────────────────────────────────
#: A position within this far of a known port (geoledger ``port`` assets) is port business, not open-water behaviour.
PORT_KM = 10.0
#: Without port data, and as a second layer with it: a position with LAND within this far (probed on a ring of points against the
#: basemap) is a port approach, a harbour or a coastal anchorage. STS / loitering is judged in open water beyond it.
COAST_KM = 6.0
COAST_PROBES = 8

# ── 3. identity changes ──────────────────────────────────────────────────────────────────────────
#: Identity evidence within the profile window: a rename (the name differs, see NAME_SAME_RATIO), an IMO number that changed on one MMSI
#: (two ships sharing a radio identity, or a spoof), an invalid IMO check digit, the same IMO under MMSIs of different flag states
#: (flag hopping), and a name that goes A -> B -> A (alternating transmissions from two sources). Each is evidence, none a verdict.
#: Each kind starts at a base confidence (how rarely an innocent cause explains it), and a sanctioned or dark-gap vessel is raised.
IDENTITY_BASE: dict[str, float] = {"rename": 0.35, "imo_change": 0.7, "imo_invalid": 0.4, "flag_hop": 0.6, "alternating": 0.6}

# ── 4. sanctioned vessel seen ────────────────────────────────────────────────────────────────────
#: A match by IMO number is high confidence; a match by exact name plus flag state is medium (names recur, flags change);
#: a name alone is never reported.
SANCTION_CONF = {"imo": 0.95, "name_flag": 0.55}
SANCTION_NAME_MIN_CHARS = 4
SANCTION_SOURCES = ("ofac", "uk", "eu")

# ── 5. loitering near sensitive infrastructure ───────────────────────────────────────────────────
#: Slow (knots) for this long inside a sensitive zone, in open water and not among a crowd (an anchorage). Cable and pipeline damage
#: needs time on station: a ship passing, or waiting its turn at an anchorage, does not.
LOITER_MAX_KN = 3.0
LOITER_MIN_S = 4 * 3600
LOITER_LOST_S = 3600
#: Ship types that work slowly on station for ordinary reasons: fishing (30), towing / dredging / diving (31-33), pilots, tugs, SAR and
#: other special craft (50-59). Their dwell is not reported. Military (35) is NOT excluded: a warship idling over a cable is the point.
LOITER_EXCLUDED_TYPES = (30, 31, 32, 33, 34, *range(50, 60))
LOITER_FULL_S = 3 * LOITER_MIN_S

# ── what is shown ────────────────────────────────────────────────────────────────────────────────
#: Event lines a section writer sees for one theater / for the sweep, and how recent an event the daily may still cite.
DESK_LINES = 6
SWEEP_LINES = 8
DESK_RECENT_DAYS = 2

# ── the long record (log.jsonl): transitions only ────────────────────────────────────────────────
#: Raw log lines are kept this many days, then only the daily summary (``daily/<day>.json.gz``, never deleted) remains. Why seven: nothing
#: reads the log back (the detectors use the profile book, the activity grid and ``events.json``), so it exists for a person asking "what
#: happened this week"; a compact line is ~0.2 KB, so a week is a few MB, while the day summaries carry the long view.
LOG_KEEP_DAYS = 7
#: A vessel's flag of one kind is written to the log at most once per this many seconds (its first line stays; the event itself still lives
#: in the picture). Each value is the least time in which a NEW event of that kind can honestly appear for the same vessel, so anything
#: sooner is the same behaviour seen again: a gap needs ``GAP_MIN_S`` of fresh silence, an encounter ``STS_MIN_S`` and a dwell
#: ``LOITER_MIN_S`` to qualify; a sanctioned sighting is one event per vessel per list entry per day, and one line per raw-log window is
#: enough for a vessel that stays in view; an identity change is evidence with its own timestamp (distinct, never repeated), so no cooldown.
LOG_COOLDOWN_S: dict[str, int] = {"ais_gap": GAP_MIN_S, "sts": STS_MIN_S, "loiter": LOITER_MIN_S, "sanctioned": LOG_KEEP_DAYS * 86400, "identity": 0}
