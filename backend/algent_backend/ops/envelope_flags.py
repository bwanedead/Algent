"""
Operating-envelope budgets (docs/architecture/foundation.md): one number per register row, each with the reason it is that number. ``newsroom
envelope`` judges every measurement against these as ok / warn / fail. Edit here when the machine or the intent changes; nothing else hard-codes them.

The machine (2026-10): DigitalOcean 2 vCPU / 4 GB RAM / 77 GB disk.
"""

from __future__ import annotations

# ── the box ──────────────────────────────────────────────────────────────────────────────────────
#: Free disk, GB (warn below, fail below). The largest transient on this disk is a one-shot job: the log compaction rewrites a log the size of the
#: log (1.7 GB before the transitions-only fix), a snapshot builds a ~0.1-0.5 GB tar in /tmp. Warn when free space is only ten times the
#: largest transient plus slack; fail when one more transient could fill it.
DISK_FREE_GB = (4.0, 10.0)
#: Available RAM, MB (fail below, warn below). 4 GB total with the stream service (~1.4 GB), SearXNG and a daily in flight: below 600 MB the next
#: model-heavy job risks the OOM killer (same floor as the doctor), below 250 MB it is already swapping.
MEM_AVAILABLE_MB = (250.0, 600.0)
#: Journald size, MB (warn above, fail above). The drop-in caps it at 200 MB (infra/server/journald-ohmega.conf); 250 MB means the cap is not
#: applied, 500 MB (it was 562 MB uncapped) means it is not working.
JOURNAL_MB = (250.0, 500.0)

# ── the stores: size and what was written in the last 7 days (MB) ────────────────────────────────
#: name -> (size warn, size fail, 7-day written warn). "Written" = bytes of files modified in the last 7 days: for an append-only store that is
#: growth, for a store that rewrites files whole it is the churn the register wants to see. Budgets are ~3x today's size (measured 2026-10-23,
#: foundation.md section 3) for stores that should hold steady, and the store's own bound where it has one.
STORE_MB: dict[str, tuple[float, float, float]] = {
    "maritime_store": (800, 3000, 800),       # profile book <= 50 000 vessels x 4 d (tens of MB) + 7 d of compact log + daily summaries; 1.7 GB log was the incident
    "library_store": (400, 1000, 400),        # crawl cache, bounded by the crawl cap; 123 MB today
    "live_store": (150, 500, 200),            # 46 MB of snapshots and baselines (relearn in ~3 weeks if lost)
    "profile_store": (300, 1500, 100),        # THE corpus: append-only, 34 MB, ~5 MB a week
    "intel_store": (250, 1500, 80),           # dailies, boards, drafts, saved visuals: ~1.4 MB a day plus ~0.3 MB of visuals
    "actors_store": (100, 500, 50),           # 17 MB, refetchable
    "geoledger_store": (100, 500, 100),       # 17 MB, rewritten per run
    "statements_store": (100, 500, 60),       # 15 MB, ~7 MB a week
    "instruments_store": (100, 500, 100),     # 9 MB, rewritten per fetch
    "markets_store": (100, 500, 100),         # 8 MB
    "sanctions_store": (100, 500, 100),       # 7 MB
    "ai_benchmarks_store": (50, 200, 50),     # 3 MB
    "pulse_store": (50, 200, 20),             # 2 MB, append-only, irreplaceable
    "draft_store": (100, 500, 50),            # paid editorial drafts
    "treatment_store": (100, 500, 50),
    "lead_store": (100, 500, 50),
}

# ── publication and backups ──────────────────────────────────────────────────────────────────────
#: R2 month-to-date uses the budget meter's own levels (database/flags.py: warn 70%, hard stop 90% of the free tier), so there is one definition.
#: The newest snapshot may be this old, hours (warn, fail): the job runs nightly at 06:40, so 30 h means a missed night, 54 h two (data_backup/flags.py).
SNAPSHOT_AGE_H = (30.0, 54.0)
#: The restore drill is monthly; stale after this many days (a month plus a week of slack).
DRILL_AGE_DAYS = 40.0

# ── feeds and search ─────────────────────────────────────────────────────────────────────────────
#: A feed is stale after this many of its own cadences plus five minutes of slack (the doctor's rule, kept the same): the timers can slip a cycle.
FEED_STALE_CADENCES = 4
#: The feeds row fails when at least this share of the feeds we have keys for are stale (one dead feed is a warning, most of them is the box).
FEED_FAIL_SHARE = 0.5
#: SearXNG results for a fixed probe query: warn below, fail at zero. A healthy instance returns 20-40; under 8 means most upstream engines
#: are blocking the datacenter IP (the failure mode in the register), 0 means search is down.
SEARCH_MIN_RESULTS = 8

# ── model spend (USD) ────────────────────────────────────────────────────────────────────────────
#: Today: warn at half the watchdog's day ceiling (ops/flags.MAX_USD_PER_DAY, which halts all paid work), fail at the ceiling.
SPEND_DAY_WARN_SHARE = 0.5
#: This month, USD (warn, fail). Scheduled paid jobs (menu, two daily editions, markets) run at a few dollars a day; ~$5 a day for a month is
#: $150, the level where the envelope's assumption has moved and a person should look; fail at double. An operator decision: edit when the intent changes.
SPEND_MONTH_USD = (150.0, 300.0)
