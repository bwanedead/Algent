"""Single-flight lock for ``newsroom run`` — one full rail spend at a time.

Killing a parent shell does not always kill the child Python on Windows. A relaunch then
overlaps the orphan and double-pays the rail (and trips analytics store-escape tripwires
when both processes touch ``draft_store`` / ``profile_store``). This lock makes the second
launch fail loudly until the first process is actually gone.
"""

from __future__ import annotations

import json
import os
import sys
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


_LOCK_NAME = "newsroom_run.lock"


class NewsroomBusyError(RuntimeError):
    """Another newsroom run still holds the single-flight lock."""


@dataclass(frozen=True)
class _Holder:
    pid: int
    started_at: str
    argv: str


def lock_path() -> Path:
    """``<runs_data>/newsroom_run.lock`` — same root as other run artifacts (env-overridable)."""
    from algent_backend.agent_system.runs.control_plane.layout import runs_data_root

    return runs_data_root() / _LOCK_NAME


def _pid_alive(pid: int) -> bool:
    """Is the recorded holder still running? Delegates to the control plane's probe.

    This used to be a local ``os.kill(pid, 0)``, which is wrong on Windows in a way that
    breaks the lock outright — and the control plane's own module already carries a comment
    saying so. ``signal.CTRL_C_EVENT == 0``, so CPython routes that call to
    ``GenerateConsoleCtrlEvent`` rather than to a liveness probe. Measured on this platform:

        live pid -> True     (right, by luck)
        DEAD pid -> True     (wrong; the house probe returns False)

    Two consequences, both observed as "the pipeline is being weird". A lock file that
    outlives its process can never be recognised as stale, so the recovery path below is
    unreachable and every later run fails "busy" until someone deletes the file by hand. And
    because the call really does try to raise a console control event, a *second* launch can
    deliver a Ctrl-C to the first run's process group — the lock interrupting the very rail it
    exists to protect.
    """
    if pid <= 0:
        return False
    from algent_backend.agent_system.runs.control_plane.liveness import process_alive

    return process_alive(pid)


def _read_holder(path: Path) -> _Holder | None:
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    try:
        return _Holder(
            pid=int(raw.get("pid") or 0),
            started_at=str(raw.get("started_at") or ""),
            argv=str(raw.get("argv") or ""),
        )
    except (TypeError, ValueError):
        return None


def _payload() -> dict[str, Any]:
    return {
        "pid": os.getpid(),
        "started_at": datetime.now(timezone.utc).isoformat(),
        "argv": " ".join(sys.argv)[:500],
    }


class NewsroomRunLock:
    """Exclusive ``O_EXCL`` lock with stale-PID recovery."""

    def __init__(self, path: Path | None = None) -> None:
        self.path = path or lock_path()
        self._held = False
        self._nested = False    # acquired inside a lock this same process already holds

    def acquire(self) -> None:
        if self._held:
            return
        self.path.parent.mkdir(parents=True, exist_ok=True)
        payload = json.dumps(_payload(), indent=2)
        for _ in range(3):
            try:
                fd = os.open(self.path, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
            except FileExistsError:
                holder = _read_holder(self.path)
                # OURS ALREADY — the lock is reentrant within one process. `newsroom run`
                # takes it and then calls `runs start` internally, which takes it again; a
                # non-reentrant lock would make the pipeline refuse its own rail. The nested
                # acquirer never writes and never releases, so the outer holder stays intact.
                if holder and holder.pid == os.getpid():
                    self._nested = True
                    self._held = True
                    return
                if holder and _pid_alive(holder.pid):
                    raise NewsroomBusyError(
                        f"newsroom already running (pid {holder.pid}"
                        + (f", since {holder.started_at}" if holder.started_at else "")
                        + "). Kill that process tree before relaunching — "
                        "overlapping rails double-spend and break analytics."
                        + (f" argv={holder.argv!r}" if holder.argv else "")
                    )
                # Stale lock from a killed shell / orphan that is actually dead.
                try:
                    self.path.unlink()
                except FileNotFoundError:
                    pass
                time.sleep(0.05)
                continue
            try:
                with os.fdopen(fd, "w", encoding="utf-8") as handle:
                    handle.write(payload)
                    handle.flush()
            except Exception:
                try:
                    os.close(fd)
                except OSError:
                    pass
                try:
                    self.path.unlink()
                except FileNotFoundError:
                    pass
                raise
            self._held = True
            return
        raise NewsroomBusyError(f"could not acquire newsroom lock at {self.path}")

    def release(self) -> None:
        if not self._held:
            return
        if self._nested:
            # Someone above us on this call stack owns the file; deleting it here would
            # unlock the rail mid-run and let a second launch straight in.
            self._held = self._nested = False
            return
        try:
            self.path.unlink()
        except FileNotFoundError:
            pass
        finally:
            self._held = False

    def __enter__(self) -> NewsroomRunLock:
        self.acquire()
        return self

    def __exit__(self, exc_type, exc, tb) -> None:
        self.release()
