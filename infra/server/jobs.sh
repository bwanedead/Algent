#!/usr/bin/env bash
# The server's scheduled jobs, one entry point so systemd units stay one-liners:
#
#   jobs.sh library | instruments | statements | backup
#
# Only FREE work runs on a schedule (crawl, public data series, statement transcripts without extraction, the
# archive backup). Anything that spends money — research, extraction, the daily, articles — runs only when the
# operator asks for it. Each job takes the same lock so two never overlap on this 4 GB machine.
set -euo pipefail
cd "$HOME/Algent/backend"
PY=".venv/bin/python"
exec 9>"$HOME/.ohmega-jobs.lock"
flock -w 3600 9

case "${1:?usage: jobs.sh library|instruments|statements|backup}" in
    library)     $PY -m algent_backend.cli newsroom library crawl --max 150 ;;
    instruments) $PY -m algent_backend.cli newsroom instruments fetch ;;
    statements)  $PY -m algent_backend.cli newsroom statements collect --no-extract --no-reported ;;
    backup)      $PY -c "from algent_backend.data_backup import sync; print(sync.backup(note='server nightly'))" ;;
    *) echo "unknown job: $1" >&2; exit 2 ;;
esac
