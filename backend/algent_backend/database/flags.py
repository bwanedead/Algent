"""
Database budget — in-repo operator knobs (no ``.env``). docs/architecture/database-budget.md explains the plan.

The database is on Supabase's FREE plan: a 500 MB database-size quota on a 1 GB disk that also holds WAL. Postgres holds only small,
relational, bounded data; every big or churny document lives in Storage (``publishing/doc_store.py``). Every number here is either a
plan fact or a window justified by what the site actually reads.
"""

from __future__ import annotations

# ── the quota (a plan fact) ──────────────────────────────────────────────────────────────────────
QUOTA_MB = 500
QUOTA_BYTES = QUOTA_MB * 1024 * 1024
#: ``newsroom doctor`` warns at this share of the quota and fails at the next. 70% leaves 150 MB (a month of the worst churn we measured
#: before this change) to react; 85% is where a VACUUM FULL, which needs room to rewrite a table, can no longer be trusted to fit.
#: Supabase Storage on the free plan: 1 GB total across the project's buckets. Documents, live snapshots and article images share it;
#: the same warn / fail shares apply (``newsroom db size`` and ``newsroom doctor`` report it).
STORAGE_QUOTA_MB = 1024
STORAGE_QUOTA_BYTES = STORAGE_QUOTA_MB * 1024 * 1024
WARN_SHARE = 0.70
FAIL_SHARE = 0.85

# ── per-write caps (derived from the quota, not guessed) ─────────────────────────────────────────
#: One Postgres row (an article's markdown, a calendar item) may be at most a thousandth of the quota: a thousand such rows still
#: fit, and an article body is tens of KB, so the cap only ever catches a runaway (a scraped page pasted whole).
ROW_CAP_BYTES = QUOTA_BYTES // 1000
#: One Storage object (a gzipped document) may be at most the bucket's own limit (migration 006 ``file_size_limit``); a larger upload
#: would be rejected by Storage anyway, so it is refused here with a clear log instead.
STORAGE_OBJECT_BYTES = 10 * 1024 * 1024

#: Parallel uploads of one publish's changed documents (a full rewrite is a few hundred small objects; the first publish after a
#: migration, or a ``force`` backfill, is the only time it matters).
UPLOAD_WORKERS = 6

# ── retention windows (days; each says what the site shows) ──────────────────────────────────────
#: Ended live events: the site's RLS shows ACTIVE rows only and nothing else reads this table, so an ended row is archive. A month
#: keeps enough history to debug a flapping feed; ~150 new events a day x ~0.6 KB = ~3 MB a month.
LIVE_EVENTS_ENDED_DAYS = 30
#: Live stats are one row per (series, UTC day). The site and the API show 45 days (``lib/live.ts``); the long baselines (live memory's
#: ``MIN_WEEKS`` / ``BASELINE_WEEKS``, instruments' ``percentile_1y``) are computed from the SERVER's stores, never from this table.
#: A year and a margin keeps a year-ago comparison one query away at ~100 series x 400 d x ~150 B = ~6 MB.
LIVE_STATS_DAYS = 400
#: Closed anomalies: the site lists active ones plus the recently closed (``liveAnomalies`` limit 200). MUST equal
#: ``live/memory/flags.RETAIN_DAYS`` (a test pins it) so the per-cycle prune and this job agree.
LIVE_ANOMALIES_DAYS = 14
#: Ended maritime events: the site's table is "current plus the last 30 days". MUST equal ``maritime/flags.RETAIN_DAYS`` (pinned);
#: the long record is the append-only ``log.jsonl`` on the server.
MARITIME_EVENTS_DAYS = 30
#: Article revisions keep the last few full markdowns per slug: enough to undo a bad rewrite or a correction; nothing reads older ones
#: (backend-only table, no grant). An article is 20-100 KB, so five is < 0.5 MB each.
REVISIONS_KEEP = 5
#: Radar sightings only mean "something new since this situation's Pulses were last assessed" (``pulse/freshness``); assessments happen
#: within days, so 90 days is generous. ~150 B x a few hundred a day.
RADAR_SIGHTINGS_DAYS = 90

# ── the prune job ────────────────────────────────────────────────────────────────────────────────
#: Rows deleted per statement/commit: small enough that one transaction never holds a table lock or produces a WAL burst on a
#: nearly full disk, large enough that a backlog clears in a handful of rounds.
PRUNE_BATCH = 2000
