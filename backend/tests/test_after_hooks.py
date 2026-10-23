"""Registry after-hooks (``Job.then``): a daily that publishes triggers the fast views build and the site smoke test, as jobs of their own, after its lock is
released; a failed job triggers nothing; a bad hook is a registry problem. Offline."""

from __future__ import annotations

import pytest

from algent_backend.ops import schedule
from algent_backend.ops.products import run as products_run, validate, views
from algent_backend.ops.products.model import Job
from algent_backend.ops.products.registry import AFTER_PUBLISH


def test_every_job_that_publishes_a_report_runs_the_fast_views_and_the_smoke_test_after() -> None:
    for name in ("daily-1", "daily-2", "markets-daily"):
        assert views.job(name)[1].then == AFTER_PUBLISH == ("views-fast", "site-smoke"), name
    assert views.job("views")[1].then == ("site-smoke",)
    smoke, fast = views.job("site-smoke")[1], views.job("views-fast")[1]
    assert smoke.spend == "free" and not smoke.lock and smoke.every_min == 60 and smoke.argv == ("site", "smoke", "--log")
    assert not fast.lock                                                       # a hook that needs the lock would wait on nothing: it runs after the daily's lock is gone
    assert validate.validate() == []


class Machine:
    """Records what ran, in order, and when the lock was held."""

    def __init__(self, monkeypatch, *, fail: set[str] = frozenset(), paid_rc: int = 0) -> None:
        self.events: list[str] = []
        self.fail, self.paid_rc = fail, paid_rc

        class Lock:
            def close(inner) -> None:  # noqa: N805
                self.events.append("released")

        def lock():
            self.events.append("taken")
            return Lock()

        def call(cmd, cwd=None):
            name = next((j.name for _, j in views.jobs() if j.argv and tuple(cmd[-len(j.argv):]) == j.argv), "?")
            self.events.append(f"ran {name}")
            return 1 if name in self.fail else 0

        monkeypatch.setattr(products_run, "acquire_lock", lock)
        monkeypatch.setattr(products_run.subprocess, "call", call)
        monkeypatch.setattr(schedule, "run_job", lambda name, *a, **k: (self.events.append(f"paid {name}") or self.paid_rc))


def test_the_hooks_run_after_a_successful_paid_job_and_after_its_lock_is_released(monkeypatch) -> None:
    m = Machine(monkeypatch)
    assert products_run.run_job("daily-1") == 0
    assert m.events == ["taken", "paid daily-1", "released", "ran views-fast", "ran site-smoke"]


def test_a_failed_job_triggers_no_hook(monkeypatch) -> None:
    m = Machine(monkeypatch, paid_rc=1)
    assert products_run.run_job("daily-1") == 1
    assert m.events == ["taken", "paid daily-1", "released"]


def test_a_failing_hook_never_changes_the_jobs_exit_code(monkeypatch, capsys) -> None:
    m = Machine(monkeypatch, fail={"views-fast"})
    assert products_run.run_job("daily-1") == 0
    assert m.events[-2:] == ["ran views-fast", "ran site-smoke"]               # the smoke test still runs: it is what notices a broken views build
    assert "after-hook views-fast of daily-1 exited 1" in capsys.readouterr().err


def test_a_hook_that_names_no_job_or_loops_is_a_registry_problem(monkeypatch) -> None:
    a = Job("a", ("x",), "*:0", every_min=5, then=("b", "ghost"))
    b = Job("b", ("y",), "*:0", every_min=5, then=("a",))
    monkeypatch.setattr(validate.views, "jobs", lambda: [(None, a), (None, b)])
    problems = validate._then_problems()
    assert any("'ghost' is not a registered timer job" in p for p in problems)
    assert any("then-chain comes back to a" in p for p in problems) and any("then-chain comes back to b" in p for p in problems)


def test_the_depth_bound_stops_a_loop_that_slipped_past_validation(monkeypatch) -> None:
    ping = Job("ping", ("ping",), "*:0", every_min=5, lock=False, then=("ping",))
    monkeypatch.setattr(products_run.views, "job", lambda name: (None, ping) if name == "ping" else None)
    calls = []
    monkeypatch.setattr(products_run.subprocess, "call", lambda cmd, cwd=None: calls.append(cmd) or 0)
    assert products_run.run_job("ping") == 0
    assert len(calls) == products_run.MAX_THEN_DEPTH + 1
