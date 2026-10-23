"""The job queue on a fake machine: priority ordering, coalescing, skip-with-reason, preemption, the memory guard, the ledger (retention, stats, peak RSS)."""

from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta

import pytest

from algent_backend.ops.jobq import flags, guard, ledger as ledger_mod, measure
from algent_backend.ops.jobq.ledger import Ledger
from algent_backend.ops.jobq.runner import Preempted, deadline_epoch, max_wait_s
from algent_backend.ops.products import validate, views
from algent_backend.ops.products.model import Job
from tests.jobq_fakes import FakeEnv, T0, queue


def J(name: str = "j", **kw) -> Job:
    return Job(name, ("x",), kw.pop("calendar", "*:0"), every_min=kw.pop("every_min", 240), **kw)


def rows(ledger: Ledger, kind: str = "run") -> list[dict]:
    return ledger.rows(kind=kind)


# ── ordering ─────────────────────────────────────────────────────────────────────────────────────
def test_a_free_lock_runs_the_job_at_once_and_ledgers_it(tmp_path) -> None:
    q, env, ledger = queue(tmp_path)
    ran = []
    assert q.run(J("corpus", priority=2), lambda: ran.append(env.t) or 0) == 0
    (r,) = rows(ledger)
    assert ran and r["outcome"] == "ok" and r["wait_s"] == 0 and r["prio"] == 2 and r["duration_s"] == 0 and not env.mine


def test_a_lower_priority_job_does_not_start_while_a_higher_one_waits(tmp_path) -> None:
    q, env, ledger = queue(tmp_path)
    env.other_waits("daily-1", 1)                            # an editorial job is in line, not yet holding
    started = []
    env.at.append((T0 + 600, lambda: env.remove(env.state_dir() / "waiting" / "daily-1.json")))   # it leaves the line (took the lock elsewhere / was skipped)
    q.run(J("backup", priority=4), lambda: started.append(env.t) or 0)
    assert started == [T0 + 600]                             # the lock was free the whole time; it still waited its turn
    assert rows(ledger)[0]["wait_s"] == 600


def test_equal_priority_goes_by_nearer_deadline_then_arrival(tmp_path) -> None:
    q, env, _l = queue(tmp_path)
    env.other_waits("late", 2, deadline=T0 + 9000, since=T0 - 50)
    env.other_waits("urgent", 2, pid=902, deadline=T0 + 100, since=T0 - 10)
    names = [e.job for e in q.line.waiting()]
    assert names == ["urgent", "late"]
    env.other_waits("plain", 2, pid=903, since=T0 - 999)     # no deadline sorts after any deadline
    assert [e.job for e in q.line.waiting()] == ["urgent", "late", "plain"]


def test_a_running_lower_priority_job_is_never_killed_the_waiter_just_waits(tmp_path) -> None:
    q, env, ledger = queue(tmp_path)
    env.other_holds("library", until=T0 + 900, prio=3)       # a collector holds the lock, not preemptible
    q.run(J("daily-1", spend="paid", every_min=1440), lambda: 0)
    assert env.terminated == [] and rows(ledger)[0]["wait_s"] == 900 and rows(ledger)[0]["waited_for"] == "library"


def test_a_preemptible_housekeeping_holder_is_terminated_when_an_editorial_job_has_waited(tmp_path, monkeypatch) -> None:
    q, env, _l = queue(tmp_path)
    env.other_holds("housekeeping", until=T0 + 100_000, prio=4, preemptible=True, pid=777)
    env.at.append((T0 + 400, lambda: setattr(env, "held_until", 0)))     # it dies on the SIGTERM
    q.run(J("daily-1", spend="paid", every_min=1440), lambda: 0)
    assert env.terminated == [777]
    # a collector of equal rank to nobody: never preempts, and with the flag off nobody does
    q2, env2, _l2 = queue(tmp_path / "b")
    monkeypatch.setattr(flags, "PREEMPT_HOUSEKEEPING", False)
    env2.other_holds("housekeeping", until=T0 + 500, prio=4, preemptible=True, pid=778)
    q2.run(J("daily-1", spend="paid", every_min=1440), lambda: 0)
    assert env2.terminated == []


def test_a_collector_never_preempts(tmp_path) -> None:
    q, env, _l = queue(tmp_path)
    env.other_holds("housekeeping", until=T0 + 500, prio=4, preemptible=True, pid=779)
    q.run(J("library", priority=3), lambda: 0)
    assert env.terminated == []


def test_a_preempted_job_ends_as_preempted_and_exits_clean(tmp_path) -> None:
    q, env, ledger = queue(tmp_path)

    def work() -> int:
        raise Preempted

    assert q.run(J("housekeeping", priority=4, preemptible=True), work) == 0
    assert rows(ledger)[0]["outcome"] == "preempted" and not env.mine


# ── coalescing and skipping ──────────────────────────────────────────────────────────────────────
def test_a_missed_slot_coalesces_into_the_job_already_waiting(tmp_path) -> None:
    q, env, ledger = queue(tmp_path)
    env.other_holds("daily-1", until=T0 + 10_000)
    env.other_waits("library", 3, pid=905)
    ran = []
    assert q.run(J("library", priority=3), lambda: ran.append(1) or 0) == 0
    (r,) = rows(ledger)
    assert not ran and r["outcome"] == "coalesced" and "already waiting" in r["reason"]


def test_a_collector_whose_previous_run_is_still_going_coalesces_but_an_editorial_job_does_not(tmp_path) -> None:
    q, env, ledger = queue(tmp_path)
    env.other_holds("library", until=T0 + 700, prio=3, pid=906)
    assert q.run(J("library", priority=3), lambda: pytest.fail("should coalesce")) == 0
    assert rows(ledger)[0]["outcome"] == "coalesced" and "already running" in rows(ledger)[0]["reason"]
    env.other_holds("daily-1", until=T0 + 60, prio=1, pid=907)
    ran = []
    q.run(J("daily-1", spend="paid", every_min=1440), lambda: ran.append(1) or 0)
    assert ran                                               # a duplicate editorial run queues behind the first instead of being dropped


def test_a_job_that_cannot_start_within_its_max_wait_is_skipped_busy_with_the_reason(tmp_path) -> None:
    q, env, ledger = queue(tmp_path)
    env.other_holds("daily-1", until=T0 + 10 ** 6)
    assert q.run(J("library", priority=3, every_min=240), lambda: pytest.fail("skipped")) == 0       # a collector's skip is policy: exit 0
    (r,) = rows(ledger)
    assert r["outcome"] == "skipped" and r["reason"].startswith("busy: lock held by daily-1") and r["wait_s"] == flags.MAX_WAIT_MIN[3] * 60
    assert not (tmp_path / "ops-log.md").exists()            # collectors do not spam the operator's journal


def test_a_skipped_editorial_job_fails_loudly_and_reaches_the_ops_log(tmp_path) -> None:
    q, env, ledger = queue(tmp_path)
    env.other_holds("x", until=T0 + 10 ** 7, prio=1)
    assert q.run(J("daily-2", spend="paid", every_min=1440), lambda: pytest.fail("skipped")) == 1
    assert rows(ledger)[0]["outcome"] == "skipped"
    log = (tmp_path / "ops-log.md").read_text(encoding="utf-8")
    assert "daily-2: SKIPPED, busy: lock held by x" in log


def test_max_wait_is_the_class_default_capped_at_the_jobs_own_cadence() -> None:
    assert max_wait_s(J(priority=3, every_min=10)) == 600                       # never past the slot that would replace it
    assert max_wait_s(J(priority=3, every_min=1440)) == flags.MAX_WAIT_MIN[3] * 60
    assert max_wait_s(J(priority=1, every_min=1440)) == flags.MAX_WAIT_MIN[1] * 60
    assert max_wait_s(J(priority=3, every_min=10, max_wait_min=90)) == 5400     # an explicit value is the operator's word


def test_a_crash_while_waiting_leaves_the_line(tmp_path) -> None:
    q, env, _l = queue(tmp_path)
    env.other_holds("x", until=T0 + 10 ** 6)
    env.at.append((T0 + 30, lambda: (_ for _ in ()).throw(KeyboardInterrupt())))
    with pytest.raises(KeyboardInterrupt):
        q.run(J("library", priority=3), lambda: 0)
    assert q.line.waiting() == []


def test_a_dead_waiters_file_does_not_block_the_line(tmp_path) -> None:
    q, env, _l = queue(tmp_path)
    env.other_waits("daily-1", 1, pid=950)
    env.alive.discard(950)                                   # it crashed
    ran = []
    q.run(J("library", priority=3), lambda: ran.append(1) or 0)
    assert ran and env.slept == 0


# ── deadlines ────────────────────────────────────────────────────────────────────────────────────
def test_deadline_is_measured_from_the_slot_and_a_miss_is_recorded(tmp_path) -> None:
    start = datetime(2026, 10, 24, 5, 31, tzinfo=UTC).timestamp()
    q, env, ledger = queue(tmp_path, t=start)
    job = Job("daily-1", ("x",), at="05:30", every_min=1440, spend="paid", deadline_min=120)
    assert deadline_epoch(job, start) == datetime(2026, 10, 24, 7, 30, tzinfo=UTC).timestamp()
    q.run(job, lambda: setattr(env, "t", env.t + 3 * 3600) or 0)             # runs 3 h: finishes 08:31, after 07:30
    assert rows(ledger)[0]["deadline_missed"] is True
    env.t = start
    q.run(job, lambda: 0)
    assert "deadline_missed" not in rows(ledger)[1]


def test_a_job_with_no_deadline_has_none() -> None:
    assert deadline_epoch(J(), T0) == 0.0


# ── memory guard ─────────────────────────────────────────────────────────────────────────────────
def test_the_guard_holds_a_job_until_memory_frees_up_and_counts_one_breach(tmp_path) -> None:
    mem = {"v": 600.0}
    q, env, ledger = queue(tmp_path, mem=lambda: mem["v"], services={"ais": 1300.0})
    env.at.append((T0 + 120, lambda: mem.update(v=3000.0)))
    q.run(J("views", priority=2, est_mb=400), lambda: 0)
    (breach,) = rows(ledger, "breach")
    assert breach["job"] == "views" and breach["need_mb"] == 400 and breach["avail_mb"] == 600
    assert rows(ledger)[0]["wait_s"] == 120 and rows(ledger)[0]["outcome"] == "ok"


def test_the_guard_skips_with_the_memory_reason_when_it_never_clears(tmp_path) -> None:
    q, env, ledger = queue(tmp_path, mem=500.0)
    assert q.run(J("library", priority=3, est_mb=300), lambda: pytest.fail("skipped")) == 0
    r = rows(ledger)[0]
    assert r["outcome"] == "skipped" and "memory: 500 MB available - 300 MB expected (registry estimate) < floor" in r["reason"]
    assert len(rows(ledger, "breach")) == 1                  # one breach per run, not one per poll


def test_the_floor_reserves_the_growth_headroom_of_the_services_that_are_running() -> None:
    # AIS is at 1000 of its 1400 peak, SearXNG not running: 400 + slack
    assert guard.floor_mb([], {"ais": 1000.0}) == 400 + flags.SLACK_MB
    # the ledger's own largest sample raises the peak
    assert guard.floor_mb([{"svc": {"ais": 1800.0}}], {"ais": 1000.0}) == 800 + flags.SLACK_MB
    assert guard.floor_mb([], {}) == flags.FLOOR_MIN_MB      # nothing seen running: only the minimum


def test_the_expected_peak_prefers_the_measured_p95_over_the_registry_estimate() -> None:
    job = J("corpus-build", priority=2, est_mb=190)
    assert guard.expected_mb(job, []) == (190, "registry estimate")
    assert guard.expected_mb(J(priority=3), []) == (flags.EST_MB[3], "class default")
    rs = [{"kind": "run", "job": "corpus-build", "outcome": "ok", "duration_s": 50, "peak_rss_mb": mb} for mb in (150, 190, 260)]
    assert guard.expected_mb(job, rs) == (260, "ledger p95")
    assert guard.expected_mb(job, rs[:2]) == (190, "registry estimate")     # too few samples to trust


def test_an_unmeasurable_machine_is_never_blocked(tmp_path) -> None:
    q, _env, _l = queue(tmp_path, mem=None)
    assert q.run(J("views", priority=2), lambda: 0) == 0


def test_lock_free_jobs_skip_the_line_and_the_guard(tmp_path) -> None:
    q, env, ledger = queue(tmp_path, mem=10.0)
    env.other_holds("daily-1", until=T0 + 10 ** 6)
    assert q.run(J("watchdog", lock=False, every_min=2), lambda: 0) == 0 and env.slept == 0
    assert rows(ledger) == []                                # fast and frequent: quiet


def test_a_slow_or_failed_lock_free_job_is_still_ledgered(tmp_path) -> None:
    q, env, ledger = queue(tmp_path)
    q.run(J("watchdog", lock=False, every_min=2), lambda: 1)
    q.run(J("update", lock=False, every_min=5), lambda: setattr(env, "t", env.t + 60) or 0)
    q.run(J("flows", lock=False, every_min=15), lambda: 0)
    assert [r["job"] for r in rows(ledger)] == ["watchdog", "update", "flows"]


# ── ledger ───────────────────────────────────────────────────────────────────────────────────────
def test_the_ledger_drops_rows_past_retention_and_caps_the_count(tmp_path, monkeypatch) -> None:
    ledger = Ledger(tmp_path / "jobs.jsonl")
    now = datetime(2026, 10, 24, tzinfo=UTC)
    ledger.append({"job": "old"}, now=now - timedelta(days=flags.LEDGER_KEEP_DAYS + 1))
    ledger.append({"job": "new"}, now=now - timedelta(days=1))
    assert ledger.compact(now=now) == 1 and [r["job"] for r in ledger.rows()] == ["new"]
    monkeypatch.setattr(flags, "LEDGER_MAX_ROWS", 3)
    for i in range(6):
        ledger.append({"job": f"n{i}"}, now=now)
    ledger.compact(now=now)
    assert [r["job"] for r in ledger.rows()] == ["n3", "n4", "n5"]


def test_the_ledger_compacts_itself_when_the_file_grows_and_survives_garbage(tmp_path, monkeypatch) -> None:
    monkeypatch.setattr(flags, "COMPACT_AT_BYTES", 300)
    monkeypatch.setattr(flags, "LEDGER_MAX_ROWS", 2)
    ledger = Ledger(tmp_path / "jobs.jsonl")
    ledger.path.write_text("not json\n", encoding="utf-8")
    now = datetime(2026, 10, 24, tzinfo=UTC)
    for i in range(8):
        ledger.append({"job": f"j{i}", "pad": "x" * 60}, now=now)
    assert len(ledger.rows()) <= 3 and ledger.rows()[-1]["job"] == "j7"
    assert Ledger(tmp_path / "missing.jsonl").rows() == []


def test_stats_give_p50_p95_wait_and_peak(tmp_path) -> None:
    rs = [{"kind": "run", "job": "views", "outcome": "ok", "duration_s": d * 60, "wait_s": w * 60, "peak_rss_mb": m}
          for d, w, m in ((1, 0, 300), (2, 0, 320), (3, 10, 340), (10, 40, 400))]
    rs += [{"kind": "run", "job": "views", "outcome": "skipped", "wait_s": 7200}, {"kind": "run", "job": "views", "outcome": "coalesced"},
           {"kind": "run", "job": "views", "outcome": "failed", "duration_s": 60, "wait_s": 0}, {"kind": "breach", "job": "views"}]
    s = ledger_mod.stats(rs)["views"]
    assert s["runs"] == 5 and s["ok"] == 4 and s["failed"] == 1 and s["skipped"] == 1 and s["coalesced"] == 1
    assert s["p50_min"] == 2 and s["p95_min"] == 10 and s["rss_p95_mb"] == 400 and s["wait_max_min"] == 120.0
    assert ledger_mod.percentile([], 95) is None and ledger_mod.percentile([5], 50) == 5


def test_a_run_records_its_peak_rss_and_service_sample(tmp_path) -> None:
    q, env, ledger = queue(tmp_path, services={"ais": 900.0})
    q.run(J("views", priority=2), lambda: measure.note_child_rss_kb(512_000) or 0)
    r = rows(ledger)[0]
    assert r["peak_rss_mb"] == 500.0 and r["svc"] == {"ais": 900.0} and r["mem_avail_mb"] == 3000


def test_a_failing_job_is_ledgered_with_its_exit_code_and_the_lock_released(tmp_path) -> None:
    q, env, ledger = queue(tmp_path)
    assert q.run(J("views", priority=2), lambda: 3) == 3
    assert rows(ledger)[0]["outcome"] == "failed" and rows(ledger)[0]["rc"] == 3 and not env.mine
    with pytest.raises(RuntimeError):
        q.run(J("views", priority=2), lambda: (_ for _ in ()).throw(RuntimeError("boom")))
    assert rows(ledger)[1]["outcome"] == "failed" and not env.mine and q.line.holder() is None


def test_peak_is_none_where_the_platform_cannot_measure() -> None:
    measure.reset()
    assert measure.peak_mb() is None
    measure.note_child_rss_kb(2048)
    assert measure.peak_mb() == 2.0


# ── registry ─────────────────────────────────────────────────────────────────────────────────────
def test_the_real_registry_ranks_paid_above_publication_above_collectors_above_housekeeping() -> None:
    prio = {j.name: j.prio for _p, j in views.timers()}
    assert prio["daily-1"] == prio["daily-2"] == prio["ai-daily"] == prio["markets-daily"] == prio["menu"] == 1
    assert prio["views"] == prio["corpus-build"] == 2 and prio["library"] == prio["live-usgs"] == 3
    assert prio["backup"] == prio["housekeeping"] == prio["db-prune"] == 4
    d1 = views.job("daily-1")[1]
    assert d1.deadline_min == 120 and d1.hhmm() == "05:30"                  # finishes by 07:30
    assert validate.validate() == []


def test_validation_rejects_a_paid_job_below_editorial_and_a_preemptible_collector(monkeypatch) -> None:
    bad = [Job("p", ("x",), at="01:00", every_min=1440, spend="paid", priority=3), Job("c", ("y",), "*:0", every_min=5, preemptible=True)]
    monkeypatch.setattr(validate.views, "jobs", lambda: [])
    from algent_backend.ops.products.model import Product

    probs = validate._product_problems(Product("t", "T", "o", "w", why="w", jobs=tuple(bad), manual="m"), {"p", "c"})
    assert any("paid jobs are always 1" in p for p in probs) and any("only housekeeping" in p for p in probs)


def test_the_line_survives_a_json_garbage_file(tmp_path) -> None:
    q, env, _l = queue(tmp_path)
    (env.state_dir() / "waiting" / "x.json").write_text("{nope", encoding="utf-8")
    assert q.line.waiting() == [] and not (env.state_dir() / "waiting" / "x.json").exists()
    json.dumps({})
