#!/usr/bin/env bash
# Install the server's systemd timers (run as ohmega; uses sudo). Idempotent: rewrites the units and restarts
# the timers. Schedules are UTC. Logs: `journalctl -u ohmega-<job> -n 50`.
#
#   ohmega-update       every 5 min    deploy-on-push (update.sh)
#   ohmega-library      every 4 h      source-library crawl (150 pages)
#   ohmega-instruments  every 6 h      free public data series
#   ohmega-statements   every 6 h      official statement transcripts (collection only, no extraction)
#   ohmega-backup       daily 06:15    stores -> private algent-data archive
set -euo pipefail
INFRA="$HOME/Algent/infra/server"

unit() {   # name, command, OnCalendar
    sudo tee "/etc/systemd/system/ohmega-$1.service" >/dev/null <<EOF
[Unit]
Description=Ohmega $1
After=network-online.target

[Service]
Type=oneshot
User=ohmega
WorkingDirectory=/home/ohmega/Algent/backend
ExecStart=/bin/bash $2
Nice=10
EOF
    sudo tee "/etc/systemd/system/ohmega-$1.timer" >/dev/null <<EOF
[Unit]
Description=Ohmega $1 schedule

[Timer]
OnCalendar=$3
Persistent=true
RandomizedDelaySec=120

[Install]
WantedBy=timers.target
EOF
}

unit update      "$INFRA/update.sh"            "*:0/5"
unit library     "$INFRA/jobs.sh library"      "0/4:20"
unit instruments "$INFRA/jobs.sh instruments"  "0/6:40"
unit statements  "$INFRA/jobs.sh statements"   "1/6:10"
unit backup      "$INFRA/jobs.sh backup"       "*-*-* 06:15"

sudo systemctl daemon-reload
for t in update library instruments statements backup; do
    sudo systemctl enable --now "ohmega-$t.timer" >/dev/null
done
systemctl list-timers 'ohmega-*' --no-pager
