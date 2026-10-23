"""
``newsroom products run <job>`` - what every systemd timer starts (through ``infra/server/jobs.sh``, a one-line router).

It looks the job up in the registry and hands it to the job queue (``ops/jobq``): a priority line for the shared job lock (one heavy job at a time on this
4 GB machine; jobs that must not wait - the watchdog, live feeds, flows, satellite - skip it), a memory guard, and a run ledger. The job's command then runs;
a paid job goes through ``ops/schedule.py`` (kill switch, runner claim, spend halt, one retry) exactly as before.
"""

from __future__ import annotations

import sys
from typing import Any

from algent_backend.ops.jobq import measure
from algent_backend.ops.jobq.runner import JobQueue

from . import views
from .model import REPO

MAX_THEN_DEPTH = 3                      # validate.py rejects chains that loop; this bounds one that slipped through


def make_queue() -> JobQueue:
    """The job queue this process uses (tests replace this with one on a fake machine)."""
    return JobQueue()


def command(job: Any) -> list[str]:
    if job.script:
        return ["bash", str(REPO / "infra" / "server" / job.script)]
    return [sys.executable, "-m", "algent_backend.cli", "newsroom", *job.argv]


def run_job(name: str, *, _depth: int = 0, _parent: str = "") -> int:
    """Run one job through the capacity-aware queue (ops/jobq/runner.py: priority line for the shared lock, memory guard, run ledger), then its ``then``
    after-hooks when it succeeded. Each hook is a job of its own (own priority, own lock turn, own spend gates) queued after this one's lock is released, so
    a hook that needs the lock cannot wait on the job that started it. A hook that fails never changes this job's exit code."""
    found = views.job(name)
    if found is None or found[1].kind != "timer":
        print(f"unknown job: {name}", file=sys.stderr)
        return 2
    job = found[1]

    def work() -> int:
        if job.spend == "paid":
            from algent_backend.ops import schedule

            return schedule.run_job(name)
        return measure.call(command(job), cwd=str(REPO / "backend"))

    rc = make_queue().run(job, work, parent=_parent)
    if rc == 0 and _depth < MAX_THEN_DEPTH:
        for hook in job.then:
            hook_rc = run_job(hook, _depth=_depth + 1, _parent=name)
            if hook_rc != 0:
                print(f"after-hook {hook} of {name} exited {hook_rc}", file=sys.stderr)
    return rc
