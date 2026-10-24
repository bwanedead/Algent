"""A paid job's one transient retry waits OUTSIDE the shared job lock and queues again through the job queue (ops/schedule.py + products/run.py)."""

from __future__ import annotations

import json

import pytest

from algent_backend.ops import flags, schedule
from algent_backend.ops.products import run as products_run
from tests.jobq_fakes import queue
from tests.test_ops_schedule import FakeProbes


class Spy(FakeProbes):
    """Records what the paid child did and whether this process held the lock when it ran."""

    def __init__(self, tmp_path, env, **kw):
        super().__init__(tmp_path, **kw)
        self.env, self.held_when_run = env, []

    def run_child(self, job, log):
        self.held_when_run.append(self.env.mine)
        return super().run_child(job, log)


def _wire(monkeypatch, tmp_path, probes_cls, results):
    q, env, ledger = queue(tmp_path)
    probes = probes_cls(tmp_path, env, results=results)
    monkeypatch.setattr(products_run, "make_queue", lambda: q)
    monkeypatch.setattr(products_run.measure, "call", lambda cmd, cwd=None: 0)          # the after-hooks (views-fast, site-smoke) must never really run here
    monkeypatch.setattr(schedule, "Probes", lambda: probes)
    monkeypatch.setattr(schedule, "journal_path", lambda: tmp_path / "scheduler.jsonl")
    return q, env, ledger, probes


def test_the_backoff_does_not_hold_the_lock_and_the_retry_queues_again(monkeypatch, tmp_path) -> None:
    q, env, ledger, probes = _wire(monkeypatch, tmp_path, Spy, [(1, "httpx.ReadTimeout: timed out"), (0, "ok")])
    during = []
    env.at.append((env.t + flags.SCHEDULED_RETRY_DELAY_MIN * 60 - 1, lambda: during.append(env.mine)))   # fires inside the back-off sleep
    start = env.t
    assert products_run.run_job("daily-1") == 0
    assert probes.ran == ["daily-1", "daily-1"] and probes.held_when_run == [True, True]
    assert during == [False], "the lock must be free while the retry waits"
    assert env.t - start >= flags.SCHEDULED_RETRY_DELAY_MIN * 60
    rows = [r for r in ledger.rows() if r.get("kind") == "run" and r["job"] == "daily-1"]
    assert [r["outcome"] for r in rows] == ["failed", "ok"] and rows[1]["parent"] == "daily-1 (retry)" and rows[1]["prio"] == 1
    assert "published" in (tmp_path / "ops-log.md").read_text(encoding="utf-8")
    assert probes.slept == []                                                     # the wait happened in the queue, not inside the lock-holding work


def test_the_retry_is_exactly_one_and_reports_both_attempts(monkeypatch, tmp_path) -> None:
    _q, _env, _ledger, probes = _wire(monkeypatch, tmp_path, Spy, [(1, "connection reset"), (1, "gateway timeout"), (0, "never")])
    assert products_run.run_job("daily-2") == 1
    assert len(probes.ran) == 2
    log = (tmp_path / "ops-log.md").read_text(encoding="utf-8")
    assert "retried once" in log and "$3.00" in log


def test_the_retry_still_obeys_the_spend_halt(monkeypatch, tmp_path) -> None:
    class HaltsAfterFirst(Spy):
        def halted(self):
            return bool(self.ran)

    _q, _env, _ledger, probes = _wire(monkeypatch, tmp_path, HaltsAfterFirst, [(1, "timed out"), (0, "ok")])
    assert products_run.run_job("daily-2") == 1 and probes.ran == ["daily-2"]
    assert json.loads((tmp_path / "scheduler.jsonl").read_text(encoding="utf-8").splitlines()[-1])["outcome"] == "skipped"


def test_the_retry_still_obeys_the_runner_claim(monkeypatch, tmp_path) -> None:
    class LosesClaim(Spy):
        def runner_status(self):
            return {"reachable": True, "is_runner": not self.ran, "runner": "other", "this_host": "me"}

    _q, _env, _ledger, probes = _wire(monkeypatch, tmp_path, LosesClaim, [(1, "timed out"), (0, "ok")])
    assert products_run.run_job("daily-2") == 1 and probes.ran == ["daily-2"]


@pytest.mark.parametrize("results", [[(1, "KeyError: 'x'")], [(1, "something odd")], [(-15, "timeout while killed")]])
def test_code_errors_unknowns_and_kills_never_wait_or_retry(monkeypatch, tmp_path, results) -> None:
    _q, env, _ledger, probes = _wire(monkeypatch, tmp_path, Spy, results + [(0, "never")])
    start = env.t
    assert products_run.run_job("menu") == 1 and len(probes.ran) == 1 and env.t - start < 60
