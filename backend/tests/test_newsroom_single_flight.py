"""Tests for newsroom single-flight lock."""

from __future__ import annotations

import json
import os
from pathlib import Path

import pytest

from algent_backend.cli.newsroom.single_flight import (
    NewsroomBusyError,
    NewsroomRunLock,
    _pid_alive,
)


def test_lock_acquire_release(tmp_path: Path) -> None:
    path = tmp_path / "newsroom_run.lock"
    lock = NewsroomRunLock(path)
    lock.acquire()
    assert path.is_file()
    data = json.loads(path.read_text(encoding="utf-8"))
    assert data["pid"] == os.getpid()
    lock.release()
    assert not path.exists()


def test_lock_blocks_second_holder(tmp_path: Path) -> None:
    path = tmp_path / "newsroom_run.lock"
    a = NewsroomRunLock(path)
    a.acquire()
    b = NewsroomRunLock(path)
    with pytest.raises(NewsroomBusyError, match="already running"):
        b.acquire()
    a.release()
    b.acquire()
    b.release()


def test_stale_lock_from_dead_pid_is_stolen(tmp_path: Path) -> None:
    path = tmp_path / "newsroom_run.lock"
    path.write_text(json.dumps({"pid": 1_999_999_999, "started_at": "", "argv": "dead"}), encoding="utf-8")
    assert not _pid_alive(1_999_999_999)
    lock = NewsroomRunLock(path)
    lock.acquire()
    assert json.loads(path.read_text(encoding="utf-8"))["pid"] == os.getpid()
    lock.release()


def test_a_dead_process_reads_as_dead() -> None:
    """The lock's whole contract rests on telling a live holder from a dead one.

    A local ``os.kill(pid, 0)`` was used here, which is not a liveness probe on Windows:
    ``signal.CTRL_C_EVENT == 0``, so CPython routes it to ``GenerateConsoleCtrlEvent``.
    Measured on Windows it returned True for an already-dead pid, so a lock file outliving
    its process could never be recognised as stale and every later run failed "busy" — and
    the same call can deliver a Ctrl-C to a live process group, letting a second launch
    interrupt the rail the lock exists to protect. The control plane already had a correct
    OpenProcess-based probe, with a comment saying exactly this.
    """
    import subprocess
    import sys
    import time

    from algent_backend.cli.newsroom import single_flight as sf

    child = subprocess.Popen([sys.executable, "-c", "import time; time.sleep(30)"])
    try:
        time.sleep(0.6)
        assert sf._pid_alive(child.pid) is True, "a running process must read as alive"
    finally:
        child.kill()
        child.wait()

    time.sleep(0.4)
    # THE regression. Measured before the fix on Windows: True for this dead pid, which made
    # the stale-lock recovery path unreachable and jammed every later run at "busy".
    assert sf._pid_alive(child.pid) is False, "a dead process must read as dead"


def test_a_dead_holder_is_recognised_as_stale(tmp_path, monkeypatch) -> None:
    """Stale-lock recovery must actually be reachable — it was dead code on Windows."""
    from algent_backend.cli.newsroom import single_flight as sf

    lock = tmp_path / "newsroom_run.lock"
    lock.write_text(json.dumps({"pid": 424242, "started_at": "", "argv": ""}), encoding="utf-8")
    monkeypatch.setattr(sf, "_pid_alive", lambda pid: False)

    with sf.NewsroomRunLock(lock):          # acquires by clearing the stale file
        assert json.loads(lock.read_text(encoding="utf-8"))["pid"] == os.getpid()


def test_a_live_holder_still_blocks(tmp_path, monkeypatch) -> None:
    from algent_backend.cli.newsroom import single_flight as sf

    lock = tmp_path / "newsroom_run.lock"
    lock.write_text(json.dumps({"pid": 4242, "started_at": "", "argv": "x"}), encoding="utf-8")
    monkeypatch.setattr(sf, "_pid_alive", lambda pid: True)

    with pytest.raises(sf.NewsroomBusyError, match="already running"):
        sf.NewsroomRunLock(lock).acquire()
