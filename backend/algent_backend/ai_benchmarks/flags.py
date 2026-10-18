"""
AI benchmark tracker — in-repo operator knobs (no ``.env``). Cadence is the systemd timers' (`infra/server/install_schedules.sh`):
the collector every 12 h, the self-reported discovery pass once a day.
"""

from __future__ import annotations

import os

# ── freshness ────────────────────────────────────────────────────────────────────────────────────
#: A source with no good fetch for this long is stale (the timer fires every 12 h; one missed run is not an alarm, three are).
STALE_HOURS = 40
#: A source whose NEWEST result is older than this many days has stopped updating upstream (leaderboards add rows at least monthly).
NEWEST_STALE_DAYS = {"epoch": 45, "swebench": 120, "lmarena": 30}
DEFAULT_NEWEST_STALE_DAYS = 90
#: A fetch that parses to fewer than this fraction of the best row count seen so far is a changed format or a truncated download, not a
#: leaderboard that lost most of its entries: it is refused (nothing appended) and the source is flagged broken.
MIN_KEEP_FRACTION = 0.6
#: A parser that cannot read more than this fraction of an Epoch bundle's benchmark files has hit a format change: the fetch fails.
MAX_BAD_BENCHMARK_FRACTION = 0.25

# ── publishing (the site document) ───────────────────────────────────────────────────────────────
#: Top models listed per benchmark in the published table, and labs given their own line per benchmark.
TOP_MODELS = 10
TOP_LABS = 6
#: A benchmark with fewer distinct models than this is listed but draws no frontier (a line through two points says nothing).
MIN_MODELS_FOR_FRONTIER = 4
#: Velocity / "recent" windows, in days.
RECENT_DAYS = 365
NEW_RECORD_DAYS = 45

# ── LMArena (rating snapshots per leaderboard publish; forward capture only) ────────────────────
LMARENA_CONFIGS: tuple[tuple[str, str], ...] = (("text", "LMArena text"), ("webdev", "LMArena web development"),
                                                 ("vision", "LMArena vision"), ("search", "LMArena search"))
LMARENA_CATEGORY = "overall"

# ── self-reported discovery (paid, capped, behind its own switch) ───────────────────────────────
#: Master switch for the daily discovery pass. False = the job exits without searching or spending.
DISCOVERY_ENABLED = True
#: Hard per-day ceilings. ONE model call a day at low effort (a few thousand input tokens) is well under the dollar cap; the tighter wins.
DISCOVERY_MAX_CALLS_PER_DAY = 1
DISCOVERY_MAX_USD_PER_DAY = 0.08
#: Per-call hard cap (cost.scoped); the call is refused by the budget gate beyond it.
DISCOVERY_CALL_CAP_USD = 0.06
#: Searches are generic (no model names): what is new is whatever the search engines surface this week.
DISCOVERY_QUERIES: tuple[str, ...] = (
    "new AI model release benchmark results",
    "AI lab announces new model state-of-the-art benchmark",
    "new open-weights language model released benchmarks",
    "model card system card benchmark scores new frontier model",
)
DISCOVERY_RESULTS_PER_QUERY = 8
DISCOVERY_MAX_PAGES = 5            # pages fetched and shown to the model
DISCOVERY_PAGE_CHARS = 3500        # characters kept per page
DISCOVERY_MAX_AGE_DAYS = 10        # results published longer ago than this are not "new"
DISCOVERY_MAX_CLAIMS = 25          # claims kept per run


def discovery_enabled() -> bool:
    raw = os.environ.get("ALGENT_AI_DISCOVERY")
    if raw is not None and raw.strip() != "":
        return raw.strip().lower() not in ("0", "false", "no", "off")
    return bool(DISCOVERY_ENABLED)
