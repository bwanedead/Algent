"""Offline tests for the spend/time watchdog: fake process probe, tmp runs_data, no signals sent."""

from __future__ import annotations

import json
import time

import pytest

from algent_backend.agent_system.foundation import live_spend
from algent_backend.ops import doctor, flags, watchdog

CMD = "python -m algent_backend.cli newsroom run --x"


class FakeProbes(watchdog.Probes):
    def __init__(self, procs):
        self._procs, self.signals = procs, []

    def processes(self):
        return self._procs

    def alive(self, pid):
        return True

    def signal(self, pid, sig):
        self.signals.append((pid, sig))

    def sleep(self, seconds):
        pass


@pytest.fixture(autouse=True)
def runs(tmp_path, monkeypatch):
    monkeypatch.setenv("ALGENT_RUNS_DIR", str(tmp_path))
    monkeypatch.setattr(flags, "KILL_GRACE_S", 0)
    live_spend._halt_checked_at = 0
    yield tmp_path
    live_spend._halt_checked_at = 0


def _heartbeat(pid, usd, now):
    d = live_spend.live_dir()
    d.mkdir(parents=True, exist_ok=True)
    (d / f"{live_spend.today()}__{pid}.json").write_text(json.dumps({"pid": pid, "started": now - 60, "usd": usd}))


def test_nothing_running_is_noop():
    out = watchdog.run_pass(FakeProbes([]))
    assert out["killed"] == [] and not live_spend.halt_path().exists()


def test_free_and_unrelated_ignored():
    procs = [watchdog.Proc(1, 99999, "python -m algent_backend.cli newsroom library crawl"),
             watchdog.Proc(2, 99999, "bash unrelated")]
    assert watchdog.watched(procs, self_pid=0) == []


def test_over_time_kills_with_term_then_kill():
    p = FakeProbes([watchdog.Proc(7, flags.MAX_MINUTES["default"] * 60 + 1, CMD)])
    out = watchdog.run_pass(p)
    assert out["killed"] == [7] and p.signals == [(7, "TERM"), (7, "KILL")]
    assert "ran" in json.loads(watchdog.log_path().read_text().splitlines()[0])["reason"]


def test_over_spend_kills_run_under_time():
    now = time.time()
    _heartbeat(8, flags.MAX_USD_PER_RUN + 1, now)
    p = FakeProbes([watchdog.Proc(8, 60, CMD)])
    assert watchdog.run_pass(p, now=now)["killed"] == [8]


def test_day_spend_halts_and_kills_all():
    now = time.time()
    _heartbeat(1, flags.MAX_USD_PER_DAY + 1, now)      # a finished process's spend still counts
    p = FakeProbes([watchdog.Proc(9, 60, CMD)])
    out = watchdog.run_pass(p, now=now)
    assert out["killed"] == [9] and out["halted"] and live_spend.halt_path().exists()
    assert watchdog.clear_halt() and not live_spend.halt_path().exists()


def test_dry_run_kills_nothing():
    p = FakeProbes([watchdog.Proc(7, 10**6, CMD)])
    out = watchdog.run_pass(p, dry_run=True)
    assert out["killed"] == [7] and p.signals == [] and not live_spend.halt_path().exists()
    assert json.loads(watchdog.log_path().read_text().splitlines()[0])["action"] == "would_kill"


def test_limits_read_from_flags(monkeypatch):
    monkeypatch.setattr(flags, "MAX_MINUTES", {"newsroom run": 5, "default": 99})
    assert watchdog.limit_minutes(CMD) == 5 and watchdog.limit_minutes("x algent_backend.cli y") == 99


def test_halt_refuses_reservations():
    from algent_backend.agent_system.foundation import cost

    live_spend.halt_path().write_text(json.dumps({"day": live_spend.today()}))
    assert cost.try_reserve(0.01, op="t") is None


def test_doctor_watchdog_check():
    class P(doctor.Probes):
        age = None

        def watchdog_age_minutes(self):
            return self.age

    p = P()
    assert doctor.check_watchdog(p)["watchdog"]["status"] == doctor.WARN
    p.age = 1.0
    assert doctor.check_watchdog(p)["watchdog"]["status"] == doctor.OK
    p.age = 60
    assert doctor.check_watchdog(p)["watchdog"]["status"] == doctor.WARN
