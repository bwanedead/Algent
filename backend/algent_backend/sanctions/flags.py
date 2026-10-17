"""
Sanctions feed — in-repo operator knobs (no ``.env``).

Cadence is the systemd timer's (`infra/server/install_schedules.sh`, every 6 h): the lists change a few times a week, a day's
worth of polling is plenty and stays polite. The numbers below are guards and reader windows, not judgements about the data.
"""

from __future__ import annotations

#: A source's FIRST snapshot is only a baseline (every listed party is "new" then). The exception: lists that date their own
#: designations (UK, EU) report the ones dated within this many days, so the feed is useful on day one.
BASELINE_RECENT_DAYS = 30

#: A later addition is dated by the list when it states a date this recent, else by the day we saw it (a list that back-dates
#: an entry by months is a correction, not news of today).
LIST_DATE_MAX_AGE_DAYS = 45

#: A new snapshot with fewer than this fraction of the previous one's entries is a truncated download or a changed format,
#: not 40% of a list delisted overnight: it is refused and the old snapshot stays.
MIN_KEEP_FRACTION = 0.6

#: Events newer than this many days are what a full re-publish sends (the site shows recent designations, not history).
PUBLISH_DAYS = 400

#: A source with no good fetch for this long is a broken feed (the doctor warns).
STALE_HOURS = 36
