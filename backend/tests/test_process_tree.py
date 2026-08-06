"""Tests for process-tree kill + timeout capture (RAM-safe nested CLI cleanup)."""

from __future__ import annotations

import subprocess
import sys
import time

import pytest

from algent_backend.agent_system.runs.control_plane import process_tree as pt
from algent_backend.agent_system.runs.control_plane.liveness import process_alive


def test_terminate_tree_on_none_is_false() -> None:
    assert pt.terminate_tree(None) is False


def test_run_capturing_completes_short_command() -> None:
    done = pt.run_capturing(
        [sys.executable, "-c", "print('ok')"],
        timeout=10.0,
    )
    assert done.returncode == 0
    assert "ok" in (done.stdout or "")


def test_run_capturing_tree_kills_on_timeout() -> None:
    """A sleeping child must not survive past the timeout (the old RAM leak)."""
    t0 = time.monotonic()
    with pytest.raises(subprocess.TimeoutExpired):
        pt.run_capturing(
            [sys.executable, "-c", "import time; time.sleep(60)"],
            timeout=1.0,
        )
    assert time.monotonic() - t0 < 15.0


def test_terminate_tree_reaps_a_live_child() -> None:
    proc = subprocess.Popen(
        [sys.executable, "-c", "import time; time.sleep(60)"],
    )
    try:
        assert process_alive(proc.pid)
        assert pt.terminate_tree(proc.pid) is True
        # Give the OS a beat to reap.
        for _ in range(20):
            if not process_alive(proc.pid):
                break
            time.sleep(0.05)
        assert not process_alive(proc.pid)
    finally:
        pt.terminate_tree(proc.pid)
