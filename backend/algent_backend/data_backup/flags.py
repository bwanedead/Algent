"""
Backup knobs (in-repo, no ``.env``). The R2 snapshot is the primary off-box copy; the git mirror is the cheap second path.
Every number says where it comes from.
"""

from __future__ import annotations

# ── the nightly R2 snapshot (data_backup/snapshot.py) ────────────────────────────────────────────
#: Where snapshots live in the PRIVATE backup bucket (``R2_BACKUP_BUCKET``). Never the public publication bucket: that one is world-readable
#: (r2.dev), and a snapshot holds unpublished drafts, leads and the corpus.
PREFIX = "backups/daily/"
#: Keep the newest 14 snapshots (two weeks of "undo yesterday"), the newest snapshot of each of the last 8 ISO weeks (two months of weekly
#: history) and of each of the last 12 months (a year). The union is at most 34 objects, usually fewer because the periods overlap.
KEEP_DAILY, KEEP_WEEKLY, KEEP_MONTHLY = 14, 8, 12
#: Envelope budgets: the nightly runs at 06:40 UTC, so a snapshot older than 30 h missed a night (warn), older than 54 h missed two (fail).
MAX_AGE_WARN_H, MAX_AGE_FAIL_H = 30, 54
#: The restore drill is monthly; one not run within 40 days (a month plus a week of slack for a missed timer) is stale.
DRILL_MAX_AGE_DAYS = 40

# ── the git mirror (data_backup/sync.py) ─────────────────────────────────────────────────────────
#: GitHub refuses a file over 100 MB outright and discourages repos over 1 GB. A file that is rewritten whole adds its compressed size to the
#: history every time it changes, so the mirror only takes files that are small relative to that wall: one tenth of the hard limit, so a file
#: must grow tenfold before it can break a push. Bigger files are covered by the R2 snapshot only.
GITHUB_FILE_LIMIT_BYTES = 100 * 1024 * 1024
MIRROR_MAX_FILE_BYTES = GITHUB_FILE_LIMIT_BYTES // 10
