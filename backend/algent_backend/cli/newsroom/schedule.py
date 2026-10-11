"""
``newsroom schedule`` — the unattended paid jobs (the geopolitics daily's editions, the menu).

    newsroom schedule run <job>     what a paid systemd unit starts (daily-1, daily-2, menu); see ``ops/schedule.py``
    newsroom schedule status        the jobs, their timer times, the kill switch and each job's last outcome (free)
    newsroom schedule times         "<job> <HH:MM>" lines, which ``infra/server/install_schedules.sh`` turns into timers

Pause everything: ``SCHEDULED_PAID_RUNS = False`` in ``ops/flags.py`` (push), or `systemctl disable --now
ohmega-daily-1.timer ohmega-daily-2.timer ohmega-menu.timer`.
"""

from __future__ import annotations

import json
from typing import Any


def add_parser(sub: Any) -> None:
    p = sub.add_parser("schedule", help="unattended paid jobs: run one, show status, list timer times")
    verbs = p.add_subparsers(dest="schedule_verb", required=True)
    r = verbs.add_parser("run", help="run one scheduled paid job (checks the kill switch, runner claim and spend halt first)")
    r.add_argument("job")
    verbs.add_parser("status", help="jobs, times, kill switch and last outcomes")
    verbs.add_parser("times", help="job names and UTC times, one per line")
    p.set_defaults(handler=run_schedule)


def run_schedule(args: Any) -> int:
    from algent_backend.ops import schedule

    if args.schedule_verb == "run":
        return schedule.run_job(args.job)
    table = schedule.jobs()
    if args.schedule_verb == "times":
        for j in table.values():
            print(f"{j.name} {j.utc}")
        return 0
    print(json.dumps({"enabled": schedule.paid_runs_enabled(),
                      "jobs": {j.name: {"utc": j.utc, "what": j.what, "last": schedule.last_outcome(j.name)}
                               for j in table.values()}}, indent=2))
    return 0
