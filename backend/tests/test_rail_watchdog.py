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


class _Clock:
    """Real time plus a jump we control — how a closed lid looks from inside the process."""

    def __init__(self) -> None:
        self.offset = 0.0

    def time(self) -> float:
        return time.time() + self.offset

    def strftime(self, fmt: str) -> str:
        return time.strftime(fmt)


def test_a_closed_lid_is_not_a_stall(monkeypatch) -> None:
    clock = _Clock()
    monkeypatch.setattr(wd, "time", clock)
    monkeypatch.setattr(wd, "_scratch_activity", lambda: 0.0)
    fired: list[int] = []
    dog = wd.Watchdog(stall_s=0.5, check_s=0.05, wake_grace_s=10, on_stall=lambda: fired.append(1))
    dog.start()
    time.sleep(0.1)
    clock.offset = 8 * 3600            # eight hours asleep
    time.sleep(0.3)
    dog.stop()
    assert fired == [] and dog._woke > 0


def test_a_run_that_stays_silent_after_waking_is_ended_on_the_short_window(monkeypatch) -> None:
    # The original 8-hour hang: a call in flight across the sleep never returns.
    clock = _Clock()
    monkeypatch.setattr(wd, "time", clock)
    monkeypatch.setattr(wd, "_scratch_activity", lambda: 0.0)
    fired: list[int] = []
    dog = wd.Watchdog(stall_s=100, check_s=0.05, wake_grace_s=0.2, on_stall=lambda: fired.append(1))
    dog.start()
    time.sleep(0.1)
    clock.offset = 3600
    time.sleep(0.7)
    dog.stop()
    assert fired == [1]


def test_a_stalled_run_relaunches_resume_once_and_banks_its_spend(tmp_path, monkeypatch) -> None:
    from algent_backend.agent_system.foundation import spend_budget as sb

    launched: list[str] = []
    monkeypatch.setattr(wd, "_launch_resume", lambda run_dir: launched.append(str(run_dir)))
    monkeypatch.setattr(wd.os, "_exit", lambda code: None)
    sb.open_envelope(5.0, 1)
    assert sb.claim("r1") == 5.0

    run = tmp_path / "0001__r1"
    wd.recover_and_exit(run_id="r1", run_dir=run, spent=lambda: 1.25)
    assert launched == [str(run)]
    # The resume reuses the run's slot, and its allowance is what is left after the dead attempt.
    assert sb.claim("r1") == 3.75

    wd.recover_and_exit(run_id="r1", run_dir=run, spent=lambda: 0.5)
    assert launched == [str(run)]                  # a second stall does not relaunch again
