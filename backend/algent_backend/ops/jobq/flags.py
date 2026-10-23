"""
Job-runner knobs (in-repo operator defaults, no ``.env``). Every number says where it comes from; the ones marked ESTIMATE are replaced by measurements as the
run ledger (``runs_data/jobs.jsonl``) fills: ``newsroom products runs`` shows the measured p50/p95 and the guard prefers them over these defaults.

The machine: one 2 vCPU / 4 GB droplet. Heavy jobs share ONE lock, so the lock's busy share is the bottleneck the capacity report measures.
"""

from __future__ import annotations

# ── priority classes (lower number runs first) ───────────────────────────────────────────────────
EDITORIAL, PUBLICATION, COLLECTOR, HOUSEKEEPING = 1, 2, 3, 4
CLASS_NAMES = {EDITORIAL: "editorial", PUBLICATION: "publication", COLLECTOR: "collector", HOUSEKEEPING: "housekeeping"}

#: How long a job may wait for the lock before it is skipped as busy, minutes, by class. Editorial reports are the product, so they outwait everything
#: (a daily takes ~70 min and two can queue behind each other); a collector's data is stale by its next slot anyway, so it is also capped at its own
#: ``every_min`` (a job never waits past the slot that would have replaced it: that is the coalescing rule).
MAX_WAIT_MIN = {EDITORIAL: 300.0, PUBLICATION: 120.0, COLLECTOR: 45.0, HOUSEKEEPING: 240.0}
POLL_S = 5.0

# ── preemption: the only way a running job is ever stopped by the queue ───────────────────────────
#: A job registered ``preemptible`` (idempotent housekeeping) is SIGTERMed when an editorial or publication job has waited this long for it. Off = never.
PREEMPT_HOUSEKEEPING = True
PREEMPT_AFTER_MIN = 3.0

# ── defaults when the ledger has no measurement yet (ESTIMATE) ───────────────────────────────────
#: Expected peak RSS, MB, by class. The only measurement so far: the corpus build peaks at 190 MB (Job.est_mb overrides).
EST_MB = {EDITORIAL: 700.0, PUBLICATION: 400.0, COLLECTOR: 250.0, HOUSEKEEPING: 150.0}
#: Expected duration, minutes, by class (Job.est_min overrides). Dailies are ~70 / ~45 min measured on the server; the rest are seconds to a few minutes.
EST_MIN = {EDITORIAL: 30.0, PUBLICATION: 2.0, COLLECTOR: 2.0, HOUSEKEEPING: 3.0}
#: A p95 is trusted only from this many ledger samples.
MIN_SAMPLES = 3

# ── memory guard ─────────────────────────────────────────────────────────────────────────────────
GUARD_ENABLED = True
#: What the resident services may still grow by, MB: floor = sum(max(service peak - service now, 0)) + SLACK, never below FLOOR_MIN. "Service peak" is
#: the largest RSS the ledger ever sampled for it, else this default. AIS ~1.4 GB (the stream service, envelope_flags.MEM_AVAILABLE_MB comment);
#: SearXNG's is an ESTIMATE (Docker, ~0.5 GB under load) until a job start samples it.
SERVICE_PEAK_MB = {"ais": 1400.0, "searxng": 600.0}
#: A process belongs to a service when every substring is in its command line.
SERVICE_MATCH = {"ais": ("algent_backend.cli", "live", "ais"), "searxng": ("searx",)}
#: Kernel, page cache churn and measurement error. FLOOR_MIN is the envelope's fail line for available RAM (250 MB: already swapping).
SLACK_MB = 150.0
FLOOR_MIN_MB = 250.0

# ── ledger ───────────────────────────────────────────────────────────────────────────────────────
LEDGER_KEEP_DAYS = 30
LEDGER_MAX_ROWS = 20000                 # ~300 B a row: 6 MB at most
COMPACT_AT_BYTES = 4_000_000
#: A lock-free job that fires more often than this and succeeds quickly is not ledgered (the watchdog's 720 runs a day would drown the signal).
LEDGER_QUIET_EVERY_MIN = 15
LEDGER_QUIET_BELOW_S = 30.0

# ── capacity and the split rule (docs/guides/worker-server.md, "When one box is not enough") ──────
#: Lock busy share of 24 h. Queueing delay grows like rho/(1-rho): at 60% a new arrival finds the lock taken 6 times in 10 and waits ~1.5 service times;
#: at 75% it waits 3. The envelope warns at 50% (still headroom for one more desk) and fails at 75% (the next desk cannot fit).
BUSY_WARN, BUSY_FAIL = 0.50, 0.75
#: The split trigger is sustained busy over 7 days at or above this, or the breaches/misses below.
SPLIT_BUSY_7D = 0.60
SPLIT_MEM_BREACHES_WEEK = 3
SPLIT_DEADLINE_MISSES_WEEK = 2
#: An hour of the day is "tight" when the lock is busy at least this share of it, averaged over the ledger days.
TIGHT_HOUR_SHARE = 0.80
