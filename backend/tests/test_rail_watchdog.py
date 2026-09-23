"""The stall watchdog: a run with no progress ends itself instead of holding the lock."""

from __future__ import annotations

import time

from algent_backend.agent_system.agents.newsroom import watchdog as wd


def test_a_silent_run_trips_the_watchdog_and_records_why(tmp_path, monkeypatch) -> None:
    monkeypatch.setattr(wd, "_scratch_activity", lambda: 0.0)
    fired: list[int] = []
    dog = wd.Watchdog(stall_s=0.2, check_s=0.05, record=tmp_path / "stalled.txt",
                      on_stall=lambda: fired.append(1))
    dog.start()
    time.sleep(0.6)
    dog.stop()
    assert fired == [1]
    assert "stalled" in (tmp_path / "stalled.txt").read_text(encoding="utf-8")


def test_events_keep_a_live_run_alive(monkeypatch) -> None:
    monkeypatch.setattr(wd, "_scratch_activity", lambda: 0.0)
    fired: list[int] = []
    dog = wd.Watchdog(stall_s=0.3, check_s=0.05, on_stall=lambda: fired.append(1))
    dog.start()
    for _ in range(10):
        dog.touch()
        time.sleep(0.05)
    dog.stop()
    assert fired == []


def test_chart_worker_file_activity_counts_as_progress(monkeypatch) -> None:
    # A chart worker draws for many minutes without a single rail event.
    monkeypatch.setattr(wd, "_scratch_activity", lambda: time.time())
    dog = wd.Watchdog(stall_s=0.1)
    dog._last = 0.0
    assert dog.idle_s() < 1


def test_the_threshold_clears_every_legitimate_silence() -> None:
    from algent_backend.agent_system.agents.editorial import analytics_worker as aw

    assert wd.STALL_S > aw._TIMEOUT_SOURCED_S
