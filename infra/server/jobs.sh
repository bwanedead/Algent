#!/usr/bin/env bash
# The one entry point of every scheduled job: `jobs.sh <job>` where <job> is a timer name in the product registry
# (backend/algent_backend/ops/products/registry.py; `newsroom products timers` lists them). The registry says what the job runs, whether it takes the
# shared job lock (one heavy job at a time on this 4 GB machine; the watchdog, live feeds, flows and satellite do not wait) and whether it is a paid job
# (those go through `ops/schedule.py`: kill switch, runner claim, spend halt, one retry). Nothing about a job is written here.
set -euo pipefail
cd "$HOME/Algent/backend"
exec .venv/bin/python -m algent_backend.cli newsroom products run "${1:?usage: jobs.sh <job>  (names: newsroom products timers)}"
