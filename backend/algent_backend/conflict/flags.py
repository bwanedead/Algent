"""
Conflict event log - in-repo operator knobs (no ``.env``; keys are env vars named in docs/credentials.md).

Cadences are the systemd timers' (`infra/server/install_schedules.sh`); the numbers here are volume guards and reader windows, not
judgements about the violence. GDELT is a machine reading of news text: the guards below keep its noise out of the record, they do not
decide what is true.
"""

from __future__ import annotations

#: GDELT is read in 15-minute files. One run catches up at most this many files (a timer that was down for three hours loses nothing; a longer
#: gap is skipped rather than replayed in one burst on a 4 GB machine).
GDELT_CATCHUP_FILES = 12
#: CAMEO root codes kept: 18 assault, 19 fight, 20 use of unconventional mass violence.
GDELT_ROOTS = ("18", "19", "20")
#: GDELT geocodes to a country centroid (type 1) or a US state (2) when the article names no place: that is a dot in the wrong place,
#: so only city / ADM1-level geocodes (3 US city, 4 world city, 5 world ADM1) are kept.
GDELT_GEO_TYPES = ("3", "4", "5")
#: An event reported by a single article is overwhelmingly a duplicate, a headline about a past event or a mis-coding; two or more
#: articles is the cheapest corroboration GDELT offers.
GDELT_MIN_ARTICLES = 2
#: Per 15-minute file, at most this many events are kept (most articles first). A normal file yields tens; this bounds a burst day.
GDELT_MAX_PER_FILE = 250
#: Articles at which a machine-coded event is labelled medium rather than low confidence.
GDELT_MEDIUM_ARTICLES = 5

#: Source urls kept per event.
MAX_URLS = 3
#: Dedupe looks at the event-date shards within this many days of an incoming event (the same attack is re-reported for a day or two).
DEDUPE_DAYS = 2

#: Windows for readers.
PUBLISH_DAYS = 30
#: The site database gets at most this many events a day (most-reported first): a bound on database growth, not on the local record.
PUBLISH_PER_DAY = 400
DESK_DAYS = 7
DESK_LINES = 8
SWEEP_LINES = 8
RETRIEVAL_DAYS = 45

#: Hours without a good fetch before the doctor calls a source stale. Keyed sources that were never configured are not broken.
STALE_HOURS = {"gdelt": 3, "reliefweb": 6, "acled": 48, "ucdp": 48}

#: A geoledger asset within this many km of an event is joined to it (a plant, depot or port the event plausibly hit).
ASSET_KM = 5.0
ASSET_MAX = 3
