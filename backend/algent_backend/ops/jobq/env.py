"""
Everything the runner touches in the world, as one object tests replace with a fake (fake clock, fake lock, fake processes, scripted memory).

The mutual exclusion is still one ``flock`` on ``~/.ohmega-jobs.lock`` (the kernel releases it if a job dies). Priority is a layer on top: a directory
``~/.ohmega-jobs.d/`` holds one small file per WAITING job (``waiting/<job>.json``: priority, deadline, since, pid) and one for the HOLDER (``holder.json``), so a
waiter can see who is ahead of it and who it is waiting for. A file whose pid is dead is ignored, so a crashed job never blocks the line.
"""

from __future__ import annotations

import json
import os
import signal
import time
from pathlib import Path
from typing import Any

from . import measure


class Env:
    def __init__(self, home: Path | None = None) -> None:
        self.home = home or Path.home()

    # ── time ──
    def now(self) -> float:
        return time.time()

    def sleep(self, seconds: float) -> None:
        time.sleep(seconds)

    # ── the lock ──
    def lock_path(self) -> Path:
        return self.home / ".ohmega-jobs.lock"

    def try_lock(self) -> Any | None:
        """The held lock (an object with ``close()``), or None when another job holds it. Where file locks do not exist (a laptop) there is nothing to overlap with: a no-op handle."""
        try:
            import fcntl
        except ImportError:
            return _Nothing()
        fh = self.lock_path().open("w")
        try:
            fcntl.flock(fh, fcntl.LOCK_EX | fcntl.LOCK_NB)
            return fh
        except OSError:
            fh.close()
            return None

    # ── the line ──
    def state_dir(self) -> Path:
        d = self.home / ".ohmega-jobs.d"
        (d / "waiting").mkdir(parents=True, exist_ok=True)
        return d

    def pid(self) -> int:
        return os.getpid()

    def pid_alive(self, pid: int) -> bool:
        try:
            os.kill(pid, 0)
            return True
        except ProcessLookupError:
            return False
        except OSError:
            return True                                       # exists but not ours (EPERM)

    def terminate(self, pid: int) -> None:
        try:
            os.kill(pid, signal.SIGTERM)
        except OSError:
            pass

    def read_json(self, path: Path) -> dict[str, Any] | None:
        try:
            return json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return None

    def write_json(self, path: Path, data: dict[str, Any]) -> None:
        try:
            path.parent.mkdir(parents=True, exist_ok=True)
            tmp = path.with_suffix(".tmp")
            tmp.write_text(json.dumps(data), encoding="utf-8")
            os.replace(tmp, path)
        except OSError:
            pass

    def remove(self, path: Path) -> None:
        try:
            path.unlink()
        except OSError:
            pass

    # ── the machine ──
    def mem_available_mb(self) -> float | None:
        return measure.mem_available_mb()

    def services_rss_mb(self) -> dict[str, float]:
        return measure.services_rss_mb()


class _Nothing:
    def close(self) -> None:
        pass
