"""Elections-feed knobs (in-repo, no ``.env``)."""

from __future__ import annotations

#: Elections taken from the calendar: those held up to this many days ago (results still being counted or certified) and those coming within the next.
LOOKBACK_DAYS = 30
LOOKAHEAD_DAYS = 120
#: Hard cap on elections fetched per run (two page fetches each, paced), calendar ones first.
MAX_ELECTIONS = 60
#: Elections named in recent poll / result asks of the prediction-market bots (passed in by the CLI; this package never reads markets) and the Wikipedia searches spent resolving them.
MAX_ASK_SEARCHES = 5
#: The recent average: the mean over the newest AVERAGE_LAST_N polls of a table that carry the party (a party missing from a poll is skipped, not counted as zero).
AVERAGE_LAST_N = 5
#: Polls kept per table in a snapshot (newest first) and tables kept per election (the ones with most polls).
MAX_POLLS_PER_TABLE = 40
MAX_TABLES = 3
#: A table row that yields fewer numbers than this is stored as raw cells (``uncertain``), not as shares.
MIN_SHARES = 2
#: Result rows kept per election.
MAX_RESULT_ROWS = 40
#: Wikipedia text is CC BY-SA 4.0: we reuse facts (numbers, names, dates) and link every item to its page.
LICENSE = "CC BY-SA 4.0"
ATTRIBUTION = "Wikipedia contributors"
CONFIDENCE = "medium"
WIKI = "https://en.wikipedia.org/wiki/{title}"
RAW = "https://en.wikipedia.org/w/index.php?title={title}&action=raw"
SEARCH = "https://en.wikipedia.org/w/api.php"
POLL_PAGE = "Opinion polling for the {election}"
#: Polls indexed per table into the corpus (newest first); every snapshot's average and results are indexed whatever this is.
INDEX_POLLS_PER_TABLE = 20
