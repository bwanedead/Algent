#!/usr/bin/env bash
# Install the server's systemd timers (run as ohmega; uses sudo). Idempotent: rewrites the units and restarts
# the timers. Schedules are UTC. Logs: `journalctl -u ohmega-<job> -n 50`.
#
#   ohmega-update       every 5 min    deploy-on-push (update.sh)
#   ohmega-library      every 4 h      source-library crawl (150 pages)
#   ohmega-instruments  every 6 h      free public data series
#   ohmega-statements   every 6 h      official statement transcripts (collection only, no extraction)
#   ohmega-sanctions    every 6 h      OFAC / UK / EU sanctions list diffs -> designation events
#   ohmega-calendar     daily 04:40    upcoming elections, central-bank decisions, summits, OPEC+, extracted deadlines
#   ohmega-markets      every 4 h      Polymarket mirror (read-only): relevant markets, prices, resolutions; paper track record
#   ohmega-backup       daily 06:15    stores -> private algent-data archive
#   ohmega-live-<feed>  every N min     free live feeds (ioda, usgs, adsb, firms; N from live/flags.py)
#   ohmega-ais          always on        AIS chokepoint counter service (needs ALGENT_AISSTREAM_KEY; restarts always)
#   ohmega-watchdog     every 2 min    kills paid runs over their time/spend limits (free; ops/flags.py)
#   ohmega-menu         daily 05:00    PAID: newsroom menu (time: MENU_UTC in ops/flags.py)
#   ohmega-daily-1      daily 05:30    PAID: geopolitics daily, part 1 Europe/Asia (time: EDITIONS in intel/flags.py)
#   ohmega-daily-2      daily 17:30    PAID: geopolitics daily, part 2 Americas, appended to the same report
# The three paid timers are operator-authorised and run unattended behind the watchdog; each job checks the kill
# switch (SCHEDULED_PAID_RUNS), the runner claim and the spend halt before it spends (ops/schedule.py). Pause:
# `sudo systemctl disable --now ohmega-menu.timer ohmega-daily-1.timer ohmega-daily-2.timer`.
set -euo pipefail
INFRA="$HOME/Algent/infra/server"
LIVE_TIMERS=""

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
unit sanctions   "$INFRA/jobs.sh sanctions"    "2/6:25"
unit calendar    "$INFRA/jobs.sh calendar"     "*-*-* 04:40"
unit markets     "$INFRA/jobs.sh markets"      "3/4:50"
unit backup      "$INFRA/jobs.sh backup"       "*-*-* 06:15"
unit watchdog    "$INFRA/jobs.sh watchdog"     "*:0/2"

# Live feeds: one timer per feed, cadence from `newsroom live schedule` (live/flags.py is the single source).
# Keyed feeds without their key just report it. A feed run is seconds long.
while read -r feed minutes; do
    # systemd minute steps only go to 59; longer cadences are written as an hourly step.
    if [ "$minutes" -ge 60 ]; then cal="*-*-* 0/$((minutes / 60)):00:00"; else cal="*:0/$minutes"; fi
    unit "live-$feed" "$INFRA/jobs.sh live $feed" "$cal"
    LIVE_TIMERS="$LIVE_TIMERS live-$feed"
done < <(cd "$HOME/Algent/backend" && .venv/bin/python -m algent_backend.cli newsroom live schedule)

# The AIS counter is a long-running service, not a timer; it exits with a message (and is retried slowly) while
# its free key is missing.
sudo tee /etc/systemd/system/ohmega-ais.service >/dev/null <<EOF
[Unit]
Description=Ohmega AIS chokepoint counter
After=network-online.target

[Service]
User=ohmega
WorkingDirectory=/home/ohmega/Algent/backend
ExecStart=/home/ohmega/Algent/backend/.venv/bin/python -m algent_backend.cli newsroom live ais
Restart=always
RestartSec=60
Nice=10

[Install]
WantedBy=multi-user.target
EOF


# Paid jobs: the times live in the repo's flags, not here (`newsroom schedule times` prints "<job> <HH:MM>").
PAID=""
while read -r job hhmm; do
    unit "$job" "$INFRA/jobs.sh $job" "*-*-* $hhmm:00"
    PAID="$PAID $job"
done < <(cd "$HOME/Algent/backend" && .venv/bin/python -m algent_backend.cli newsroom schedule times)
[ -n "$PAID" ] || { echo "no paid jobs listed by 'newsroom schedule times'; refusing to continue" >&2; exit 1; }

sudo systemctl daemon-reload
for t in update library instruments statements sanctions calendar markets backup watchdog $LIVE_TIMERS $PAID; do
    sudo systemctl enable --now "ohmega-$t.timer" >/dev/null
done
sudo systemctl enable --now ohmega-ais.service >/dev/null
systemctl list-timers 'ohmega-*' --no-pager
