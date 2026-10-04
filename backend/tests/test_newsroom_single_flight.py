"""Tests for newsroom single-flight lock."""

from __future__ import annotations

import json
import os
from types import SimpleNamespace
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


def test_lock_blocks_a_second_PROCESS(tmp_path: Path, monkeypatch) -> None:
    """The contract is one rail per MACHINE, enforced across processes.

    This used to assert that two lock objects in one process blocked each other, which
    reads as the same thing and is not: the rail is launched by `newsroom run`, which then
    calls `runs start` — both of which take the lock, in one process. Blocking on
    same-pid made the pipeline refuse its own rail, so nesting is allowed and the guard
    is against a DIFFERENT live pid, which is the case that actually double-spends.
    """
    from algent_backend.cli.newsroom import single_flight as sf

    path = tmp_path / "newsroom_run.lock"
    path.write_text(json.dumps({"pid": 4242, "started_at": "", "argv": "other run"}),
                    encoding="utf-8")
    monkeypatch.setattr(sf, "_pid_alive", lambda pid: pid == 4242)

    with pytest.raises(NewsroomBusyError, match="already running"):
        NewsroomRunLock(path).acquire()

    # Once that process is gone, the lock is recoverable rather than jammed forever.
    monkeypatch.setattr(sf, "_pid_alive", lambda pid: False)
    lock = NewsroomRunLock(path)
    lock.acquire()
    assert json.loads(path.read_text(encoding="utf-8"))["pid"] == os.getpid()
    lock.release()
    assert not path.exists()


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


def test_the_lock_is_reentrant_within_one_process(tmp_path) -> None:
    """`newsroom run` holds the lock and then calls `runs start`, which takes it again.

    A non-reentrant lock makes the pipeline refuse its own rail — the holder pid IS us and
    is trivially alive, so the busy check fires on ourselves.
    """
    from algent_backend.cli.newsroom import single_flight as sf

    lock = tmp_path / "newsroom_run.lock"
    outer = sf.NewsroomRunLock(lock)
    outer.acquire()
    try:
        inner = sf.NewsroomRunLock(lock)
        inner.acquire()                       # must not raise
        inner.release()
        # The nested release must NOT remove the file — that would unlock the rail mid-run.
        assert lock.exists(), "nested release deleted the outer holder's lock"
        assert json.loads(lock.read_text(encoding="utf-8"))["pid"] == os.getpid()
    finally:
        outer.release()
    assert not lock.exists()


def test_launching_the_rail_directly_also_takes_the_lock(tmp_path, monkeypatch) -> None:
    """The hole that `newsroom run`'s lock did not cover: `runs start newsroom_rail`
    bypassed single-flight entirely, so the same overlapping spend was one command away."""
    from algent_backend.cli.newsroom import single_flight as sf
    from algent_backend.cli.runs import start

    lock = tmp_path / "newsroom_run.lock"
    lock.write_text(json.dumps({"pid": 4242, "started_at": "", "argv": "other"}), encoding="utf-8")
    monkeypatch.setattr(sf, "lock_path", lambda: lock)
    monkeypatch.setattr(sf, "_pid_alive", lambda pid: pid == 4242)

    code = start.run(SimpleNamespace(agent_id="newsroom_rail"))
    assert code == 2                          # refused, not launched


def test_a_non_rail_agent_is_not_gated(monkeypatch) -> None:
    """Only full-rail spend is single-flight; a cheap agent must still run alongside one."""
    from algent_backend.cli.runs import start

    monkeypatch.setattr(start, "_run", lambda args: 0)
    assert start.run(SimpleNamespace(agent_id="discovery_synthesis")) == 0
