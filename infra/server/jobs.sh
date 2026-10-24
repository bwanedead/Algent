#!/usr/bin/env bash
# The server's scheduled jobs, one entry point so systemd units stay one-liners:
#
#   jobs.sh library | instruments | statements | sanctions | calendar | markets | ai-benchmarks | ai-discovery | backup | watchdog | flows | conflict | reliefweb | conflict-daily | gnss | satellite | live <feed>   free
#   jobs.sh menu | daily-1 | daily-2 | markets-daily                       PAID, unattended (operator-authorised)
#
# Free work: crawl, AI benchmark scores, a capped (<$0.10/day, ai_benchmarks/flags.py) discovery of lab-claimed scores, public data series, statement transcripts without extraction, the archive backup.
# The paid jobs are exactly four: the newsroom menu, the geopolitics daily's two editions and the Polymarket paper trader's day (markets-daily). They go through
# `newsroom schedule run`, which refuses to spend unless SCHEDULED_PAID_RUNS is on (ops/flags.py), this machine holds
# the runner claim and no spend halt stands; it retries a transient failure once; the watchdog bounds the child.
# Everything else that spends (articles, ad-hoc research) still runs only when the operator asks.
# Each job takes the same lock so two never overlap on this 4 GB machine (menu then daily just queue).
set -euo pipefail
cd "$HOME/Algent/backend"
PY=".venv/bin/python"
# The watchdog must fire while a long job holds the lock below, so it runs before (and without) it.
if [ "${1:-}" = "watchdog" ]; then exec $PY -m algent_backend.cli newsroom watchdog; fi
# Live feeds are seconds long and must keep listening while a daily holds the lock, so they skip it too.
if [ "${1:-}" = "live" ]; then exec $PY -m algent_backend.cli newsroom live run --feed "${2:?usage: jobs.sh live <feed>}"; fi
# The flows document (lane aggregates the stream service wrote + the weekly Comtrade refresh, a couple of minutes at most) is free and independent of the lock too.
if [ "${1:-}" = "flows" ]; then exec $PY -m algent_backend.cli newsroom flows publish; fi
# The conflict log and the GNSS pass are light (seconds to ~1.5 min), keep their own state and run on short cadences: no lock, so a daily never delays them.
case "${1:-}" in
    conflict)       exec $PY -m algent_backend.cli newsroom conflict fetch --source gdelt ;;
    reliefweb)      exec $PY -m algent_backend.cli newsroom conflict fetch --source reliefweb ;;
    conflict-daily) exec $PY -m algent_backend.cli newsroom conflict fetch --source acled --source ucdp ;;
    gnss)           exec $PY -m algent_backend.cli newsroom gnss run ;;
esac
# The satellite pass (a dozen keyless imagery lookups, a few minutes, daily) is free and stays out of the lock too: it must not wait behind a daily.
if [ "${1:-}" = "satellite" ]; then exec $PY -m algent_backend.cli newsroom satellite run; fi
exec 9>"$HOME/.ohmega-jobs.lock"
flock -w 3600 9

case "${1:?usage: jobs.sh library|instruments|statements|sanctions|calendar|conflict|reliefweb|conflict-daily|gnss|markets|ai-benchmarks|ai-discovery|backup|live|menu|daily-1|daily-2|markets-daily}" in
    library)     $PY -m algent_backend.cli newsroom library crawl --max 150 ;;
    instruments) $PY -m algent_backend.cli newsroom instruments fetch ;;
    statements)  $PY -m algent_backend.cli newsroom statements collect --no-extract --no-reported ;;
    sanctions)   $PY -m algent_backend.cli newsroom sanctions fetch ;;
    calendar)    $PY -m algent_backend.cli newsroom calendar refresh ;;
    markets)     $PY -m algent_backend.cli newsroom markets refresh ;;
    ai-benchmarks) $PY -m algent_backend.cli newsroom ai-benchmarks fetch ;;
    ai-discovery)  $PY -m algent_backend.cli newsroom ai-benchmarks discover ;;
    backup)      $PY -c "from algent_backend.data_backup import sync; print(sync.backup(note='server nightly'))" ;;
    menu|daily-1|daily-2|markets-daily|ai-daily) $PY -m algent_backend.cli newsroom schedule run "$1" ;;
    *) echo "unknown job: $1" >&2; exit 2 ;;
esac
