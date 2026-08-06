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
