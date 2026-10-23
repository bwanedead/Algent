"""
``newsroom products run <job>`` - what every systemd timer starts (through ``infra/server/jobs.sh``, a one-line router).

It looks the job up in the registry and hands it to the job queue (``ops/jobq``): a priority line for the shared job lock (one heavy job at a time on this
4 GB machine; jobs that must not wait - the watchdog, live feeds, flows, satellite - skip it), a memory guard, and a run ledger. The job's command then runs;
a paid job goes through ``ops/schedule.py`` (kill switch, runner claim, spend halt, one retry) exactly as before.
"""

from __future__ import annotations

import os
import sys
from typing import Any

from algent_backend.ops import flags as ops_flags, status
from algent_backend.ops.jobq import measure
from algent_backend.ops.jobq.runner import JobQueue
from algent_backend.publishing import changed

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


def _run_paid(queue: JobQueue, job: Any, name: str, parent: str) -> int:
    """A paid job: the first attempt through the line; if it failed transiently, the lock is already released while the back-off runs and the one retry
    queues again at the job's own (editorial) priority. The kill switch, runner claim and spend halt are re-checked by the retry itself (ops/schedule.py)."""
    from algent_backend.ops import schedule

    schedule.clear_last()
    carry: list[dict[str, Any]] = []
    rc = queue.run(job, lambda: schedule.run_job(name, attempt=1, carry=carry), parent=parent)
    if rc != schedule.RETRY_LATER:
        return rc
    print(f"{name}: transient failure; the lock is free for {ops_flags.SCHEDULED_RETRY_DELAY_MIN:g} min, then one retry queues again", flush=True)
    queue.env.sleep(ops_flags.SCHEDULED_RETRY_DELAY_MIN * 60)
    return queue.run(job, lambda: schedule.run_job(name, attempt=2, carry=carry), parent=f"{name} (retry)")


def _verdict(queue: JobQueue, job: Any) -> str:
    """"ok" / "failed" when the job really ran to a result, "" when it was skipped, coalesced, preempted or (paid) held back by policy: those never
    count as the product having been checked."""
    if job.spend == "paid":
        from algent_backend.ops import schedule

        return {"published": "ok", "failed": "failed"}.get(str(schedule.last_event().get("outcome")), "")
    return queue.outcome if queue.outcome in ("ok", "failed") else ""


def run_job(name: str, *, _depth: int = 0, _parent: str = "") -> int:
    """Run one job through the capacity-aware queue (ops/jobq/runner.py: priority line for the shared lock, memory guard, run ledger), then its ``then``
    after-hooks when it succeeded. Each hook is a job of its own (own priority, own lock turn, own spend gates) queued after this one's lock is released, so
    a hook that needs the lock cannot wait on the job that started it. A hook that fails never changes this job's exit code."""
    found = views.job(name)
    if found is None or found[1].kind != "timer":
        print(f"unknown job: {name}", file=sys.stderr)
        return 2
    product, job = found

    queue = make_queue()
    previous = os.environ.get(changed.ENV)
    os.environ[changed.ENV] = product.id if product else ""            # the job's process notes what it really uploads under this product (publishing/changed.py)
    try:
        if job.spend == "paid":
            rc = _run_paid(queue, job, name, _parent)
        else:
            rc = queue.run(job, lambda: measure.call(command(job), cwd=str(REPO / "backend")), parent=_parent)
    finally:
        if previous is None:
            os.environ.pop(changed.ENV, None)
        else:
            os.environ[changed.ENV] = previous
    if product and (verdict := _verdict(queue, job)):
        status.record(product, name, verdict == "ok")  # one PUT per successful run per publishing product (ops/status.py)
    if rc == 0 and _depth < MAX_THEN_DEPTH:
        for hook in job.then:
            hook_rc = run_job(hook, _depth=_depth + 1, _parent=name)
            if hook_rc != 0:
                print(f"after-hook {hook} of {name} exited {hook_rc}", file=sys.stderr)
    return rc
