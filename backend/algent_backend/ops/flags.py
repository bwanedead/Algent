"""
Watchdog limits — in-repo operator knobs for ``newsroom watchdog`` (no ``.env``).

These are a floor against runaway API bills, not a budget: set generous so legitimate work never trips them,
low enough that a stuck loop is stopped within hours. Per-article hard caps and spend envelopes still do the
fine-grained capping; the watchdog catches what those cannot (a hung process, a loop that never ends, a bug in
the caps themselves).
"""

from __future__ import annotations

#: Wall-clock ceiling per kind of run, in minutes. First entry whose key appears in the command line wins
#: (order matters: specific before general). ``default`` covers every other paid-looking algent command.
#: The geopolitics daily with research legitimately takes ~70 min (edition 2 is shorter: only what is new) and a
#: menu ~30 min, hence the generosity. The scheduled jobs (``ops/schedule.py``) start the SAME commands, so the same
#: limits cover them; the scheduler's own wrapper is a free command and is not timed. A retry after a transient
#: failure is a fresh process with a fresh clock, so one scheduled job can legitimately span two of these windows.
MAX_MINUTES: dict[str, int] = {
    "intel daily": 180,
    "newsroom run": 180,
    "newsroom resume": 180,
    "default": 180,
}

#: Free scheduled/maintenance subcommands that never spend and are never watched or killed.
FREE_COMMANDS: tuple[str, ...] = (
    "watchdog", "doctor", "envelope", "backup", "runner", "budget", "library", "instruments", "statements", "corpus", "reads", "live", "schedule", "sanctions", "calendar", "flows", "satellite",
)

#: Kill a single process once its own settled spend (live_spend heartbeat) passes this many USD. Article hard
#: caps default to $3, a daily with research runs a handful of articles: this is a loop detector, not a plan.
#: Scheduled editions sit well under it: a full daily with research and a spotlight has cost a few dollars, edition 2
#: less (it reuses edition 1's research); $15 stays because a ceiling that real work can brush would kill a good
#: run, and the $40 day ceiling below is what actually protects the month (menu + two editions + one retry each fit).
MAX_USD_PER_RUN = 15.0

#: Across all processes today (UTC): past this, kill everything paid and write the spend-halt marker so the
#: budget gate (``cost.try_reserve``) refuses new billable work until tomorrow or ``--clear-halt``.
MAX_USD_PER_DAY = 40.0

#: SIGTERM first so the run can pause cleanly and settle its envelope; SIGKILL after this many seconds.
KILL_GRACE_S = 20

#: Heartbeat files older than this many days are deleted by a pass.
LIVE_SPEND_KEEP_DAYS = 3

#: ``newsroom doctor`` warns when the last pass is older than this (the timer fires every 2 minutes).
DOCTOR_STALE_MINUTES = 10


# ── scheduled PAID runs (ops/schedule.py; units installed by infra/server/install_schedules.sh) ──────────────
#: Master switch for the unattended paid jobs (the geopolitics daily's two editions and the newsroom menu). False =
#: every scheduled paid job logs "paused" and exits without spending, with no unit changes needed; commit + push
#: and the server's deploy-on-push picks it up. The harder stop is `systemctl disable --now ohmega-daily-*
#: ohmega-menu.timer`. ``ALGENT_SCHEDULED_PAID_RUNS=0`` in the process env overrides for a one-off.
SCHEDULED_PAID_RUNS = True

#: When the newsroom menu job fires (UTC, HH:MM). The daily editions' times are ``intel/flags.EDITIONS``. The menu
#: goes first so the operator wakes to it; the lock in jobs.sh makes it and edition 1 run in sequence, never together.
MENU_UTC = "05:00"

#: A failed scheduled run is retried ONCE after this many minutes, and only when the failure looks transient (below).
#: Research is reused by the daily (saved profiles), so a retry never buys the same research twice.
SCHEDULED_RETRY_DELAY_MIN = 30

#: Log text that marks a failure as transient (network / provider hiccup): worth one retry. Matched
#: case-insensitively against the tail of the run's output.
TRANSIENT_MARKERS: tuple[str, ...] = (
    "timeout", "timed out", "connection reset", "connection aborted", "connection refused", "remote end closed",
    "remoteprotocolerror", "apiconnectionerror", "readerror", "temporarily unavailable", "service unavailable",
    "overloaded", "bad gateway", "gateway timeout", "502", "503", "504", "429", "rate limit", "name resolution",
)

#: Exception names that mean OUR code is wrong: never retried, even if a transient marker also appears (a retry would
#: only fail the same way, or spend again). A watchdog kill (SIGTERM/SIGKILL exit) is never retried either.
CODE_ERROR_MARKERS: tuple[str, ...] = (
    "attributeerror", "typeerror", "keyerror", "nameerror", "importerror", "modulenotfounderror", "indexerror",
    "assertionerror", "syntaxerror", "validationerror", "valueerror", "notimplementederror", "unboundlocalerror",
)

#: How many trailing log lines the classifier and the ops-log summary look at.
OUTCOME_TAIL_LINES = 120
