"""Capacity: calendar parsing, the modelled day (same rule as the real queue), busy share from the ledger, the one-more-desk projection, the split rule, the report text."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

from algent_backend.ops.jobq import capacity, flags, render
from algent_backend.ops.jobq.capacity import Cost, daily_starts, simulate
from algent_backend.ops.jobq.ledger import Ledger
from algent_backend.ops.products import views
from algent_backend.ops.products.model import Job

NOW = datetime(2026, 10, 24, 12, 0, tzinfo=UTC)


def at(name: str, hhmm: str, **kw) -> Job:
    return Job(name, ("x",), at=hhmm, every_min=kw.pop("every_min", 1440), **kw)


def costs(**mins: float) -> dict[str, Cost]:
    return {n: Cost(m, 200.0, "estimate") for n, m in mins.items()}


def test_every_calendar_form_in_the_registry_parses_to_minutes_of_the_day() -> None:
    assert daily_starts("*:0/2")[:3] == [0, 2, 4] and len(daily_starts("*:0/2")) == 720
    assert daily_starts("*-*-* 03:20") == [200]
    assert daily_starts("2/6:25") == [2 * 60 + 25, 8 * 60 + 25, 14 * 60 + 25, 20 * 60 + 25]
    assert daily_starts("*:17") == [h * 60 + 17 for h in range(24)]
    assert daily_starts("*:7/15")[:4] == [7, 22, 37, 52]
    assert daily_starts("*-*-* 0/4:00:00") == [0, 240, 480, 720, 960, 1200]
    assert daily_starts("*-*-01 07:30:00") == []                       # monthly: no ordinary day
    for _p, j in views.timers():
        assert j.when() and (daily_starts(j.when()) or j.name == "backup-drill"), j.name


def test_the_model_serves_editorial_before_housekeeping_even_when_housekeeping_arrived_first() -> None:
    jobs = [at("backup", "05:25", priority=4), at("daily-1", "05:30", spend="paid"), at("menu", "05:00", spend="paid")]
    sim = simulate(jobs, costs(backup=5, **{"daily-1": 70, "menu": 30}))
    order = [r["job"] for r in sorted(sim.runs, key=lambda r: r["start"])]
    # menu 05:00-05:30; at 05:30 daily-1 (editorial) and backup (waiting since 05:25) are both ready: the editorial job goes first
    assert order == ["menu", "daily-1", "backup"]
    run = {r["job"]: r for r in sim.runs}
    assert run["backup"]["wait"] == 70 + 5 and run["daily-1"]["wait"] == 0


def test_the_model_coalesces_a_collector_that_would_pile_up_and_skips_one_past_its_max_wait() -> None:
    long_job = at("daily-1", "00:00", spend="paid")
    fast = Job("library", ("x",), "*:0/10", every_min=10)                       # fires every 10 min, may wait 10 min at most
    sim = simulate([long_job, fast], costs(**{"daily-1": 120, "library": 1}))
    outcomes = [r["outcome"] for r in sim.runs if r["job"] == "library"]
    assert "skipped" in outcomes and outcomes.count("ok") > 100             # it is skipped while the daily runs, and runs normally afterwards
    waiting = [r for r in sim.runs if r["job"] == "library" and r["wait"] > 10]
    assert all(r["outcome"] == "skipped" for r in waiting)


def test_after_hooks_are_queued_when_their_parent_ends() -> None:
    jobs = [at("daily-1", "05:30", spend="paid", then=("views-fast",)), at("views-fast", "23:50", priority=2)]
    sim = simulate(jobs, costs(**{"daily-1": 60, "views-fast": 2}))
    hook = next(r for r in sim.runs if r["job"] == "views-fast" and r["parent"] == "daily-1")
    assert hook["arrive"] == capacity.DAY_MIN + 5 * 60 + 30 + 60 and hook["wait"] == 0


def test_busy_share_is_a_union_of_locked_runs_over_the_window() -> None:
    t = NOW.timestamp()
    rows = [{"kind": "run", "job": "a", "locked": True, "start": t - 7200, "end": t - 3600},
            {"kind": "run", "job": "b", "locked": True, "start": t - 5400, "end": t - 1800},       # overlaps a: counted once
            {"kind": "run", "job": "c", "locked": False, "start": t - 600, "end": t - 60}]
    assert abs(capacity.busy_share(rows, NOW, 4) - (5400 / (4 * 3600))) < 1e-9


def test_queue_health_counts_waits_skips_breaches_and_misses(tmp_path) -> None:
    ledger = Ledger(tmp_path / "j.jsonl")
    recent, old = NOW - timedelta(hours=2), NOW - timedelta(days=3)
    ledger.append({"job": "views", "prio": 2, "outcome": "ok", "wait_s": 1200.0, "locked": True, "start": 1.0, "end": 2.0}, now=recent)
    ledger.append({"job": "library", "prio": 3, "outcome": "skipped", "reason": "busy: x"}, now=recent)
    ledger.append({"job": "library", "prio": 3, "outcome": "coalesced"}, now=recent)
    ledger.append({"kind": "breach", "job": "views"}, now=recent)
    ledger.append({"job": "daily-1", "prio": 1, "outcome": "ok", "deadline_missed": True, "wait_s": 0}, now=old)
    h = capacity.queue_health(ledger.rows(), NOW)
    assert h["24h"]["waited"] == 1 and h["24h"]["wait_p95_min"] == 20 and len(h["24h"]["skipped"]) == 1 and h["24h"]["coalesced"] == 1
    assert h["24h"]["breaches"] == 1 and h["24h"]["deadline_missed"] == [] and h["7d"]["deadline_missed"] == ["daily-1"]


def test_the_split_rule_names_each_clause_that_holds() -> None:
    quiet = {"busy_7d": 0.2, "7d": {"breaches": 0, "deadline_missed": [], "skipped": []}}
    assert capacity.split_triggers(quiet) == []
    busy = {"busy_7d": 0.65, "7d": {"breaches": 4, "deadline_missed": ["daily-1", "daily-2"], "skipped": [{"job": "menu", "prio": 1}]}}
    got = capacity.split_triggers(busy, projected_busy=0.7)
    assert len(got) == 5 and "memory-floor breaches" in got[1] and "planned desk" in got[-1]
    assert capacity.split_triggers({**quiet, "7d": {**quiet["7d"], "skipped": [{"job": "library", "prio": 3}]}}) == []     # a skipped collector is not a split reason


def test_a_new_desk_adds_its_own_minutes_and_lands_in_the_quietest_slot() -> None:
    jobs = [at("daily-1", "05:30", spend="paid"), at("menu", "05:00", spend="paid"), Job("ai-daily", ("x",), at="09:00", every_min=1440, spend="paid")]
    c = costs(**{"daily-1": 70, "menu": 30, "ai-daily": 40})
    base = simulate(jobs, dict(c))
    p = capacity.project_new_desk(jobs, c, base, "ai-daily")
    assert p["added_busy_min"] == 40 and p["added_wait_min"] == 0 and p["skips_after"] == 0
    assert p["busy_after"] > p["busy_before"] and p["best_slot"] not in ("05:00", "05:30", "06:00")
    assert capacity.project_new_desk(jobs, c, base, "nope") is None


def test_the_report_and_its_text_on_the_real_registry_without_a_ledger(tmp_path) -> None:
    r = capacity.report(Ledger(tmp_path / "none.jsonl"), now=NOW)
    assert 0.05 < r["model"]["busy_share"] < flags.SPLIT_BUSY_7D and r["split"] == [] and r["new_desk"]["like"] == "ai-daily"
    assert r["model"]["sources"]["ledger"] == [] and "daily-1" in r["model"]["sources"]["estimate"]
    text = render.capacity_text(r)
    assert "MODELLED day" in text and "ONE MORE DESK" in text and "SPLIT RULE: no clause holds" in text


def test_measured_durations_replace_estimates_once_there_are_enough_runs(tmp_path) -> None:
    ledger = Ledger(tmp_path / "j.jsonl")
    for m in (50, 60, 90):
        ledger.append({"job": "daily-1", "prio": 1, "outcome": "ok", "duration_s": m * 60, "wait_s": 0, "locked": True, "peak_rss_mb": 900}, now=NOW - timedelta(days=1))
    r = capacity.report(ledger, now=NOW)
    assert "daily-1" in r["model"]["sources"]["ledger"] and "daily-1" not in r["model"]["sources"]["estimate"]


def test_runs_text_lists_jobs_with_p50_p95_and_wait(tmp_path) -> None:
    ledger = Ledger(tmp_path / "j.jsonl")
    ledger.append({"job": "views", "prio": 2, "outcome": "ok", "duration_s": 120.0, "wait_s": 600.0, "peak_rss_mb": 410}, now=NOW - timedelta(hours=1))
    ledger.append({"job": "library", "prio": 3, "outcome": "skipped", "reason": "busy: lock held by daily-1", "wait_s": 2700}, now=NOW - timedelta(hours=2))
    text = render.runs_text(render.runs_data(ledger, 7, NOW))
    assert "views" in text and "410" in text and "skipped" in text and "busy: lock held by daily-1" in text
    assert "no runs recorded" in render.runs_text(render.runs_data(Ledger(tmp_path / "x.jsonl"), 7, NOW))
