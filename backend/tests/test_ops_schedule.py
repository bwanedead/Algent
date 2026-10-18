"""Unattended paid jobs: they run only when allowed, retry once for transient failures only, and always leave a line."""

from __future__ import annotations

from datetime import UTC, datetime

import pytest

from algent_backend.ops import doctor, flags, schedule


class FakeProbes(schedule.Probes):
    def __init__(self, tmp_path, *, runner=True, reachable=True, halted=False, results=(), spend_per_run=1.5):
        self.tmp, self._runner, self._reachable, self._halted = tmp_path, runner, reachable, halted
        self.results, self.ran, self.slept, self._spend, self._per = list(results), [], [], 0.0, spend_per_run

    def editions_done(self, day):
        return {1}

    def runner_status(self):
        return {"reachable": self._reachable, "is_runner": self._runner, "runner": "other" if not self._runner else "me",
                "this_host": "me"}

    def halted(self):
        return self._halted

    def day_spend(self):
        return self._spend

    def run_child(self, job, log):
        self.ran.append(job.name)
        rc, tail = self.results.pop(0)
        self._spend += self._per
        return rc, tail

    def sleep(self, seconds):
        self.slept.append(seconds)

    def home(self):
        return self.tmp

    def now(self):
        return datetime(2026, 10, 12, 5, 30, tzinfo=UTC)


@pytest.fixture(autouse=True)
def _journal(tmp_path, monkeypatch):
    monkeypatch.setattr(schedule, "journal_path", lambda: tmp_path / "scheduler.jsonl")
    monkeypatch.delenv("ALGENT_SCHEDULED_PAID_RUNS", raising=False)


def _oplog(tmp_path) -> str:
    return (tmp_path / "ops-log.md").read_text(encoding="utf-8")


def test_jobs_and_their_times_come_from_the_flags() -> None:
    table = schedule.jobs()
    assert set(table) == {"menu", "daily-1", "daily-2", "markets-daily", "ai-daily"}  # ai-daily: operator-authorised 2026-10-18
    assert table["menu"].utc == flags.MENU_UTC and table["daily-1"].utc == "05:30" and table["daily-2"].utc == "17:30"
    assert "--edition" in table["daily-2"].argv and table["daily-2"].argv[-1] == "2" and "--research" in table["daily-2"].argv
    assert table["menu"].argv == ("run", "--to", "menu")
    assert table["markets-daily"].argv == ("markets", "daily") and table["markets-daily"].utc > table["daily-1"].utc


def test_a_successful_run_is_logged_with_spend_and_link(tmp_path) -> None:
    p = FakeProbes(tmp_path, results=[(0, "ok")])
    assert schedule.run_job("daily-1", p) == 0
    line = _oplog(tmp_path)
    assert "· scheduler" in line and "daily-1: published" in line and "$1.50" in line
    assert "https://www.ohmega.monster/geopolitics/2026-10-12" in line
    assert schedule.last_outcome("daily-1")["outcome"] == "published"


@pytest.mark.parametrize("kw,why", [({"runner": False}, "not the runner"), ({"reachable": False}, "unreachable"),
                                    ({"halted": True}, "spend halt")])
def test_it_does_not_spend_unless_it_is_the_runner_and_nothing_is_halted(tmp_path, kw, why) -> None:
    p = FakeProbes(tmp_path, results=[(0, "")], **kw)
    assert schedule.run_job("daily-2", p) == 0
    assert p.ran == [] and why in _oplog(tmp_path)


def test_the_kill_switch_pauses_every_job(tmp_path, monkeypatch) -> None:
    monkeypatch.setattr(flags, "SCHEDULED_PAID_RUNS", False)
    p = FakeProbes(tmp_path, results=[(0, "")])
    assert schedule.run_job("menu", p) == 0 and p.ran == [] and "paused" in _oplog(tmp_path)
    monkeypatch.setattr(flags, "SCHEDULED_PAID_RUNS", True)
    monkeypatch.setenv("ALGENT_SCHEDULED_PAID_RUNS", "0")
    assert schedule.run_job("menu", p) == 0 and p.ran == []


def test_a_transient_failure_is_retried_once_after_the_delay(tmp_path) -> None:
    p = FakeProbes(tmp_path, results=[(1, "httpx.ReadTimeout: timed out"), (0, "ok")])
    assert schedule.run_job("daily-2", p) == 0
    assert p.ran == ["daily-2", "daily-2"] and p.slept == [flags.SCHEDULED_RETRY_DELAY_MIN * 60]
    assert "published" in _oplog(tmp_path) and "$3.00" not in _oplog(tmp_path).split("published")[0]


def test_a_code_error_is_never_retried(tmp_path) -> None:
    p = FakeProbes(tmp_path, results=[(1, "Traceback...\nKeyError: 'x'\nread timed out earlier"), (0, "ok")])
    assert schedule.run_job("daily-1", p) == 1
    assert p.ran == ["daily-1"] and p.slept == [] and "FAILED" in _oplog(tmp_path) and "not retried" in _oplog(tmp_path)


def test_an_unknown_failure_and_a_watchdog_kill_are_not_retried(tmp_path) -> None:
    for rc, tail in ((1, "something odd"), (-15, "timeout while killed")):
        p = FakeProbes(tmp_path, results=[(rc, tail), (0, "ok")])
        assert schedule.run_job("menu", p) == 1 and p.ran == ["menu"]


def test_a_second_transient_failure_is_reported_not_retried_again(tmp_path) -> None:
    p = FakeProbes(tmp_path, results=[(1, "connection reset"), (1, "gateway timeout")])
    assert schedule.run_job("daily-2", p) == 1
    assert len(p.ran) == 2 and "retried once" in _oplog(tmp_path)


def test_the_retry_rechecks_the_halt(tmp_path) -> None:
    class HaltsAfterFirst(FakeProbes):
        def halted(self):
            return bool(self.ran)

    p = HaltsAfterFirst(tmp_path, results=[(1, "timed out"), (0, "ok")])
    assert schedule.run_job("daily-2", p) == 1 and p.ran == ["daily-2"]


def test_the_watchdog_ignores_the_free_scheduler_wrapper_but_not_its_child() -> None:
    from algent_backend.ops import watchdog

    wrapper = watchdog.Proc(10, 5.0, "python -m algent_backend.cli newsroom schedule run daily-1")
    child = watchdog.Proc(11, 5.0, "python -m algent_backend.cli newsroom intel daily --edition 2 --research")
    assert watchdog.watched([wrapper, child], self_pid=1) == [child]


def test_doctor_reports_the_paid_timers_and_their_last_outcome(tmp_path) -> None:
    class P(doctor.Probes):
        def timer_state(self, job):
            return "enabled" if job != "menu" else "not-found"

        def scheduled_jobs(self):
            return {"daily-1": {"utc": "05:30", "last": {"outcome": "failed", "ts": "2026-10-11T05:40:00+00:00", "usd": 2.0,
                                                         "why": "exit 1, code"}},
                    "menu": {"utc": "05:00", "last": None}}

        def scheduled_enabled(self):
            return True

    out = doctor.check_schedule(P())
    assert out["schedule:daily-1"]["status"] == doctor.WARN and "failed" in out["schedule:daily-1"]["detail"]
    assert out["schedule:menu"]["status"] == doctor.WARN and "not-found" in out["schedule:menu"]["detail"]

    class Q(P):
        def timer_state(self, job):
            return None

        def scheduled_enabled(self):
            return False

    out = doctor.check_schedule(Q())
    assert out["schedule"]["status"] == doctor.WARN and out["schedule:menu"]["status"] == doctor.OK


def test_part_two_waits_for_part_one(monkeypatch, tmp_path) -> None:
    from algent_backend.ops import schedule

    calls = []

    class P(schedule.Probes):
        def editions_done(self, day):
            return set()

        def run_child(self, job, log):
            calls.append(job.name)
            return 0, ""

        def home(self):
            return tmp_path

    monkeypatch.setattr(schedule, "_record", lambda outcome: None)
    monkeypatch.setattr(schedule, "_ops_log", lambda probes, line: None)
    assert schedule.run_job("daily-2", P()) == 0
    assert calls == []
