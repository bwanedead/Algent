#!/usr/bin/env bash
# Install the server's systemd timers (run as ohmega; uses sudo). Idempotent: rewrites the units and restarts
# the timers. Schedules are UTC. Logs: `journalctl -u ohmega-<job> -n 50`.
#
# Timers, systemd units and their schedules (UTC) are NOT listed here: the product registry owns them (backend/algent_backend/ops/products/registry.py).
# `newsroom products timers` prints "<name><TAB><command><TAB><OnCalendar>" for every timer (free jobs, live feeds from live/flags.py, the paid jobs
# whose times come from intel/flags.py, ops/flags.py and markets/flags.py) and this script writes one service+timer pair per line. The one always-on
# service (ohmega-ais) is written below. Logs: `journalctl -u ohmega-<job> -n 50`. `newsroom products check` (also in `newsroom doctor`) lists
# timers that are installed but registered to nobody (orphans) and registered ones that are missing.
#
# The paid timers (spend="paid" in the registry) are operator-authorised and run unattended behind the watchdog; each job checks the kill
# switch (SCHEDULED_PAID_RUNS), the runner claim and the spend halt before it spends (ops/schedule.py). Pause: `newsroom schedule times` lists them,
# then `sudo systemctl disable --now ohmega-<job>.timer` for each, or flip SCHEDULED_PAID_RUNS in ops/flags.py and push.
set -euo pipefail
INFRA="$HOME/Algent/infra/server"
PY="$HOME/Algent/backend/.venv/bin/python"

# Cap the journal (200 MB; journald-ohmega.conf). Needs sudo like the units below; idempotent. The vacuum trims what is already there once.
sudo install -D -m 0644 "$INFRA/journald-ohmega.conf" /etc/systemd/journald.conf.d/ohmega.conf
sudo systemctl restart systemd-journald
sudo journalctl --vacuum-size=200M >/dev/null 2>&1 || true

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

# Every timer in the registry: name, command (relative to infra/server), OnCalendar. Refuse to continue on an empty list: a half-installed set is worse than none.
TIMERS=""
while IFS=$'	' read -r name cmd cal; do
    unit "$name" "$INFRA/$cmd" "$cal"
    TIMERS="$TIMERS $name"
done < <(cd "$HOME/Algent/backend" && "$PY" -m algent_backend.cli newsroom products timers)
[ -n "$TIMERS" ] || { echo "no timers listed by 'newsroom products timers'; refusing to continue" >&2; exit 1; }

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


sudo systemctl daemon-reload
for t in $TIMERS; do
    sudo systemctl enable --now "ohmega-$t.timer" >/dev/null
done
sudo systemctl enable --now ohmega-ais.service >/dev/null
systemctl list-timers 'ohmega-*' --no-pager
