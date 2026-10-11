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
#: The geopolitics daily with research legitimately takes ~70 min and a menu ~30 min, hence the generosity.
MAX_MINUTES: dict[str, int] = {
    "intel daily": 180,
    "newsroom run": 180,
    "newsroom resume": 180,
    "default": 180,
}

#: Free scheduled/maintenance subcommands that never spend and are never watched or killed.
FREE_COMMANDS: tuple[str, ...] = (
    "watchdog", "doctor", "runner", "budget", "library", "instruments", "statements", "corpus", "reads", "live",
)

#: Kill a single process once its own settled spend (live_spend heartbeat) passes this many USD. Article hard
#: caps default to $3, a daily with research runs a handful of articles: this is a loop detector, not a plan.
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
