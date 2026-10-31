"""The prospective lab: contested live markets asked at 'now', forecast blind by every active protocol under a day budget, scored once the markets resolve."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from types import SimpleNamespace

import pytest

from algent_backend.experiment import branches, calibrate, flags, policies, prospective, qset, runner, score, sources, store, tournament
from algent_backend.experiment.contracts import Evidence, Question
from algent_backend.markets import store as ms
from algent_backend.markets.contracts import Market, Snapshot

DOCS = [Evidence(id="d1", kind="daily", source="t", title="talks", body="Talks stalled over monitors", publish_time="2026-01-01", acquired_at="2026-01-01")]
SRC = sources.ListSource(DOCS)


@pytest.fixture(autouse=True)
def stores(tmp_path, monkeypatch):
    monkeypatch.setenv("ALGENT_EXPERIMENT_STORE", str(tmp_path / "lab"))
    monkeypatch.setenv("ALGENT_MARKETS_STORE", str(tmp_path / "markets"))


def market(mid, event, *, theater="iran", hours=72, liq=5000.0, vol=20000.0, **kw):
    return Market(id=mid, event_id=event, question=f"Will thing {mid} happen?", description="rules", end_date=(datetime.now(UTC) + timedelta(hours=hours)).isoformat(),
                  theaters=[theater] if theater else [], liquidity=liq, volume=vol, **kw)


def seed(markets, prices):
    ms.save_markets(markets)
    now = datetime.now(UTC)
    ms.append_snapshots([Snapshot(market_id=mid, at=(now - timedelta(hours=1)).isoformat(timespec="seconds"), p=p) for mid, p in prices.items()])


def ask(p, usd):
    return lambda task, role: (SimpleNamespace(probability=p, rationale="r", cited=["d1"]), usd)


def seed_protocols(usd=0.02):
    """Two controlled protocols with a stored run each, so they count as active."""
    p0 = policies.freeze_blind_forecaster()
    p1 = policies.replace_policy(p0, policies.evidence_policy("keyword-overlap", k=4), "p1")
    q = Question(id="seed", text="seed?", cutoff="2026-01-02T00:00:00+00:00", reference={"market_p": 0.5})
    runner.run_controlled(q, [branches.ensure("p0", p0), branches.ensure("p1", p1)], SRC, lambda proto: ask(0.4, usd), live=True)
    return p0, p1


def test_selection_rules_contested_horizon_floor_family_and_round_robin():
    seed([market("ok1", "e1"), market("ok2", "e2", theater="taiwan"), market("ok3", "e3", theater="ukraine"), market("ok4", "e4", theater="ukraine"),
          market("sib", "e1", liq=900.0 + 5000.0),                                      # same event as ok1, deeper: it is the one taken for e1
          market("decided", "e5", ), market("thin", "e6", liq=10.0), market("soon", "e7", hours=5), market("far", "e8", hours=500),
          market("stale", "e9"), market("closed", "e10", status="resolved", outcome="yes")],
         {"ok1": 0.4, "ok2": 0.5, "ok3": 0.6, "ok4": 0.3, "sib": 0.45, "decided": 0.97, "thin": 0.5, "soon": 0.5, "far": 0.5, "closed": 0.5})
    chosen, skipped = prospective.select(datetime.now(UTC), limit=10)
    ids = [m.id for m in chosen]
    assert set(ids) == {"sib", "ok2", "ok3", "ok4"} and skipped["same_event"] == 1
    assert skipped["not_contested"] == 1 and skipped["thin"] == 1 and skipped["horizon"] == 2 and skipped["no_fresh_price"] == 1 and skipped["not_open"] == 1
    assert [qset.topic(m) for m in chosen[:3]] == ["iran", "taiwan", "ukraine"]       # round-robin across topics: ukraine's second market comes after the first of each
    assert len(prospective.select(datetime.now(UTC), limit=2)[0]) == 2


def test_build_asks_at_now_with_the_price_at_the_cutoff_and_never_asks_a_market_twice():
    seed([market("a", "e1"), market("b", "e2")], {"a": 0.35, "b": 0.65})
    now = datetime.now(UTC)
    doc = prospective.build(now)
    qs = qset.questions_of(doc)
    assert doc["stored"] and len(qs) == 2 and all(q.cutoff == now.isoformat(timespec="seconds") and q.common_set and q.category == "live" for q in qs)
    assert {q.source: q.reference["market_p"] for q in qs} == {"market:a": 0.35, "market:b": 0.65}
    assert store.read_lines("sets/index.jsonl") == [] and len(store.read_lines(prospective.INDEX)) == 1        # `--set latest` stays the historical set
    again = prospective.build(now + timedelta(minutes=5))
    assert not again["stored"] and again["skipped"]["already_asked"] == 2
    assert prospective.build(now, dry_run=True)["stored"] is False
    union = qset.load("prospective")
    assert union["id"] == "prospective" and {e["source"] for e in union["questions"]} == {"market:a", "market:b"}


def test_the_daily_quota_counts_questions_already_asked_today(monkeypatch):
    monkeypatch.setattr(flags, "PROSPECTIVE_MARKETS", 3)
    seed([market(f"m{i}", f"e{i}") for i in range(6)], {f"m{i}": 0.5 for i in range(6)})
    now = datetime.now(UTC)
    assert prospective.build(now)["quota_left"] == 3 and len(qset.load("prospective")["questions"]) == 3
    assert prospective.build(now + timedelta(minutes=1))["quota_left"] == 0
    assert len(qset.load("prospective")["questions"]) == 3
    assert len(prospective.build(now + timedelta(days=1))["questions"]) == 3                 # tomorrow: a fresh quota, the other three markets


def test_budget_stops_cleanly_pairs_protocols_and_a_rerun_continues_without_repaying():
    seed_protocols(usd=0.02)
    seed([market(f"m{i}", f"e{i}", theater=t) for i, t in enumerate(["iran", "taiwan", "ukraine"])], {"m0": 0.4, "m1": 0.5, "m2": 0.6})
    now = datetime.now(UTC)
    prospective.build(now)
    day = now.date().isoformat()
    assert len(prospective.active_protocols()) == 2
    est = prospective.estimate(prospective.active_protocols()[0])
    assert est == pytest.approx(qset.max_cost(policies.freeze_blind_forecaster()))            # fewer than 3 stored runs: the per-run maximum
    out = prospective.run(day, SRC, lambda proto: ask(0.3, 0.03), budget_usd=0.10)
    assert len(out["ran"]) == 2 and out["stopped"] and out["not_run"] == 4 and out["spent_usd"] == pytest.approx(0.06)      # 0.06 spent + 0.05 estimate > 0.10: stops before the third call
    first_q = {r["question"] for r in out["ran"]}
    assert len(first_q) == 1 and {r["protocol"] for r in out["ran"]} == set(prospective.active_protocols())      # the first question was answered by BOTH protocols: paired
    log = store.read_lines(prospective.LOG)
    assert log[-1]["ran"] == 2 and log[-1]["stopped"] and log[-1]["spent_usd"] == pytest.approx(0.06)
    assert prospective.spent_today(day) == pytest.approx(0.06)
    more = prospective.run(day, SRC, lambda proto: ask(0.3, 0.03), budget_usd=1.0)             # same day, bigger budget: continues, never repeats a stored run
    assert more["reused"] == 2 and len(more["ran"]) == 4 and not more["stopped"] and more["spent_earlier_today_usd"] == pytest.approx(0.06)
    assert prospective.run(day, SRC, lambda proto: ask(0.3, 0.03), budget_usd=1.0)["ran"] == []


def test_the_order_rotates_with_the_date_and_retired_protocols_are_skipped():
    p0, p1 = seed_protocols()
    assert prospective.rotate([1, 2, 3], "2026-10-30") != prospective.rotate([1, 2, 3], "2026-10-31") and prospective.rotate([], "2026-10-31") == []
    assert sorted(prospective.rotate([1, 2, 3], "2026-10-31")) == [1, 2, 3]
    assert set(prospective.active_protocols()) == {p0.id, p1.id}
    from algent_backend.experiment import genealogy

    genealogy.retire(p1.id, "worse")
    assert prospective.active_protocols() == [p0.id]


def test_a_dry_run_stores_and_calls_nothing():
    seed_protocols()
    seed([market("a", "e1")], {"a": 0.5})
    out = prospective.run_day(source=SRC, ask_for=lambda proto: (_ for _ in ()).throw(AssertionError("no model call")), live=False)
    assert out["live"] is False and len(out["would_ask"]) == 1 and not store.read_lines(prospective.INDEX) and not store.read_lines(prospective.LOG)


def test_results_flow_into_scoring_calibration_and_the_tournament_once_the_market_resolves():
    seed_protocols()
    seed([market("a", "e1"), market("b", "e2", theater="taiwan")], {"a": 0.4, "b": 0.6})
    out = prospective.run_day(source=SRC, ask_for=lambda proto: ask(0.3, 0.01), live=True)
    assert out["new_questions"] == 2 and len(out["ran"]) == 4 and not out["stopped"]
    qs = {q.source: q for q in qset.questions_of(qset.load("prospective"))}
    assert all(r.live for r in score.runs() if r.question_id in {q.id for q in qs.values()})
    assert score.scoreboard()["unresolved"] and not calibrate.lab_rows()                     # nothing resolved yet: asked, not scored
    done = ms.markets()["a"].model_copy(update={"status": "resolved", "outcome": "no", "resolved_at": datetime.now(UTC).isoformat(timespec="seconds")})
    ms.save_markets([done])
    rows = [r for r in calibrate.lab_rows() if r["question"] == qs["market:a"].id]
    assert len(rows) == 2 and {r["market_p"] for r in rows} == {0.4} and {r["o"] for r in rows} == {0}
    board = qset.board(qset.load("prospective"))
    assert board["n_questions"] == 2 and all(p["n"] == 1 for p in board["protocols"].values())
    qs_order = tournament.order(qset.load("prospective"))
    assert {q.id for q in qs_order} == {q.id for q in qs.values()}
