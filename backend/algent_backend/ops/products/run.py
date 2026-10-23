"""
``newsroom products run <job>`` - what every systemd timer starts (through ``infra/server/jobs.sh``, a one-line router).

It looks the job up in the registry, takes the shared job lock when the job asks for it (one heavy job at a time on this 4 GB machine; jobs that
must not wait - the watchdog, live feeds, flows, satellite - skip it), then runs the job's command. A paid job goes through ``ops/schedule.py``
(kill switch, runner claim, spend halt, one retry) exactly as before.
"""

from __future__ import annotations

import subprocess
import sys
import time
from pathlib import Path
from typing import Any

from . import views
from .model import REPO

LOCK_WAIT_S = 3600


def lock_path() -> Path:
    return Path.home() / ".ohmega-jobs.lock"


def acquire_lock(wait_s: float = LOCK_WAIT_S) -> Any | None:
    """Hold the shared lock until the returned handle is closed. None where file locks do not exist (a laptop): there is nothing to overlap with."""
    try:
        import fcntl
    except ImportError:
        return None
    fh = lock_path().open("w")
    deadline = time.monotonic() + wait_s
    while True:
        try:
            fcntl.flock(fh, fcntl.LOCK_EX | fcntl.LOCK_NB)
            return fh
        except OSError:
            if time.monotonic() >= deadline:
                fh.close()
                raise TimeoutError(f"job lock still held after {wait_s:.0f} s") from None
            time.sleep(5)


def command(job: Any) -> list[str]:
    if job.script:
        return ["bash", str(REPO / "infra" / "server" / job.script)]
    return [sys.executable, "-m", "algent_backend.cli", "newsroom", *job.argv]


def run_job(name: str) -> int:
    found = views.job(name)
    if found is None or found[1].kind != "timer":
        print(f"unknown job: {name}", file=sys.stderr)
        return 2
    job = found[1]
    lock = acquire_lock() if job.lock else None
    try:
        if job.spend == "paid":
            from algent_backend.ops import schedule

            return schedule.run_job(name)
        return subprocess.call(command(job), cwd=str(REPO / "backend"))
    finally:
        if lock is not None:
            lock.close()
