#!/usr/bin/env bash
# The server's scheduled jobs, one entry point so systemd units stay one-liners:
#
#   jobs.sh library | instruments | statements | backup | watchdog       free
#   jobs.sh menu | daily-1 | daily-2                                      PAID, unattended (operator-authorised)
#
# Free work: crawl, public data series, statement transcripts without extraction, the archive backup.
# The paid jobs are exactly three: the newsroom menu and the geopolitics daily's two editions. They go through
# `newsroom schedule run`, which refuses to spend unless SCHEDULED_PAID_RUNS is on (ops/flags.py), this machine holds
# the runner claim and no spend halt stands; it retries a transient failure once; the watchdog bounds the child.
# Everything else that spends (articles, ad-hoc research) still runs only when the operator asks.
# Each job takes the same lock so two never overlap on this 4 GB machine (menu then daily just queue).
set -euo pipefail
cd "$HOME/Algent/backend"
PY=".venv/bin/python"
# The watchdog must fire while a long job holds the lock below, so it runs before (and without) it.
if [ "${1:-}" = "watchdog" ]; then exec $PY -m algent_backend.cli newsroom watchdog; fi
exec 9>"$HOME/.ohmega-jobs.lock"
flock -w 3600 9

case "${1:?usage: jobs.sh library|instruments|statements|backup|menu|daily-1|daily-2}" in
    library)     $PY -m algent_backend.cli newsroom library crawl --max 150 ;;
    instruments) $PY -m algent_backend.cli newsroom instruments fetch ;;
    statements)  $PY -m algent_backend.cli newsroom statements collect --no-extract --no-reported ;;
    backup)      $PY -c "from algent_backend.data_backup import sync; print(sync.backup(note='server nightly'))" ;;
    menu|daily-1|daily-2) $PY -m algent_backend.cli newsroom schedule run "$1" ;;
    *) echo "unknown job: $1" >&2; exit 2 ;;
esac
