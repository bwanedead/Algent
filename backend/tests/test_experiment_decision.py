"""Frozen trader and day bot as controls, and decision replay scored by realised P&L (stubbed models, temp stores)."""

from __future__ import annotations

from types import SimpleNamespace

import pytest

from algent_backend.experiment import branches, controls, decision, policies, runner, score, sources, store
from algent_backend.experiment.contracts import Evidence, Question
from algent_backend.markets import store as ms
from algent_backend.markets.contracts import Market, Snapshot

CUTOFF = "2026-03-10T12:00:00+00:00"
Q = Question(id="q1", text="Will Aldoria and Brevia sign a ceasefire by 2026-03-31?", rules="Resolves YES if signed.", cutoff=CUTOFF, closes_at="2026-03-31T00:00:00+00:00",
             source="market:m1")
DOCS = [Evidence(id="d1", kind="daily", source="t", title="talks", body="Talks stalled over monitors", publish_time="2026-03-01", acquired_at="2026-03-01")]


@pytest.fixture(autouse=True)
def stores(tmp_path, monkeypatch):
    monkeypatch.setenv("ALGENT_EXPERIMENT_STORE", str(tmp_path / "lab"))
    monkeypatch.setenv("ALGENT_MARKETS_STORE", str(tmp_path / "markets"))
    ms.save_markets([Market(id="m1", question=Q.text, description=Q.rules, end_date=Q.closes_at, status="resolved", outcome="yes", resolved_at="2026-03-25T00:00:00+00:00")])
    ms.append_snapshots([Snapshot(market_id="m1", at="2026-03-08T06:00:00+00:00", p=0.35), Snapshot(market_id="m1", at="2026-03-10T06:00:00+00:00", p=0.40),
                         Snapshot(market_id="m1", at="2026-03-20T06:00:00+00:00", p=0.95)])         # the last one is AFTER the cutoff: the trader must never see it


def forecast_run(p: float = 0.7):
    p0 = policies.freeze_blind_forecaster()
    b = branches.ensure("p0", p0)
    ask = lambda task, role: (SimpleNamespace(probability=p, rationale="base rate then talks", cited=["d1"]), 0.01)      # noqa: E731
    return runner.run_controlled(Q, [b], sources.ListSource(DOCS), lambda proto: ask)[0]


def trader(action: str, stake: float = 300.0):
    seen: list[str] = []

    def ask(task: str, role: str):
        seen.append(task)
        return SimpleNamespace(decisions=[SimpleNamespace(market="M1", action=action, stake_usd=stake, rationale="the crowd is slow", cited=["d1", "nope"])]), 0.02

    ask.seen = seen  # type: ignore[attr-defined]
    return ask


def test_trader_and_day_bot_are_frozen_as_protocols_and_stay_frozen():
    t, d = controls.freeze_trader(), controls.freeze_day_bot()
    assert t.policies["prompts"].params["role"].startswith("You run a paper-money portfolio") and t.policies["decision"].params["bankroll"] == 10000.0
    assert t.policies["evidence"].ref == "evidence/production-research@1" and t.policies["decision"].impl_sha and not controls.impl_drift_decision(t)
    assert "buy" in d.policies["tools"].params["names"] and d.policies["prompts"].params["role"] and d.policies["decision"].ref == "decision/paper-guards-day@1"
    assert store.read_json("frozen/trader.json")["replayable"] is True and store.read_json("frozen/day-bot.json")["replayable"] is False
    assert controls.freeze_trader().id == t.id and controls.freeze_day_bot().id == d.id            # a second call returns the stored capture


def test_replay_shows_the_state_at_the_cutoff_and_fills_at_the_cutoff_price():
    run, t = forecast_run(), controls.freeze_trader()
    ask = trader("buy_yes")
    rec = decision.replay(Q, t, run, ask, live=True)
    task = ask.seen[0]
    assert "YES 40% / NO 60%" in task and "95%" not in task and "The desk's own probability of YES: 70%" in task and "Talks stalled" in task
    assert rec.action == "buy_yes" and rec.side == "yes" and rec.price == pytest.approx(0.41) and rec.cash_flow == -300.0 and rec.cited == ["d1"]
    assert rec.market_p == 0.40 and rec.desk_p == 0.7 and rec.usd == 0.02
    assert decision.replay(Q, t, run, trader("sell")).id == rec.id and len(ask.seen) == 1             # the same decision is not asked (or paid for) twice


def test_the_guards_clip_the_request_like_production():
    run, t = forecast_run(), controls.freeze_trader()
    rec = decision.replay(Q, t, run, trader("buy_yes", 5000.0))
    assert rec.cash_flow == -500.0 and any("position limit" in c for c in rec.clips)


def test_decisions_are_scored_by_realised_pnl_apart_from_forecast_scoring():
    run, t = forecast_run(), controls.freeze_trader()
    decision.replay(Q, t, run, trader("buy_yes"))
    day = controls.freeze_day_bot()                                                                  # a second "protocol" id to pair against: it holds
    hold_run = SimpleNamespace(run_id=run.run_id, p=run.p)
    held = decision.DecisionRecord(id="h1", question_id=Q.id, protocol_id=day.id, forecast_run=hold_run.run_id, action="hold")
    store.write_once("decisions/h1/decision.json", held)
    b = decision.board()
    won = b["protocols"][t.id]
    assert won["trades"] == 1 and won["staked"] == 300.0 and won["pnl"] == pytest.approx(300 / 0.41 - 300, abs=0.01) and won["return_on_stake"] > 0.4
    assert b["protocols"][day.id]["pnl"] == 0.0 and b["protocols"][day.id]["trades"] == 0
    pair = next(iter(b["differences"].values()))
    assert pair["n_shared"] == 1 and pair["se"] is None                                              # one question is an anecdote
    assert "modes" not in b and "decisions" not in score.scoreboard()["modes"].get("controlled", {}).get("protocols", {})   # forecast scoring is untouched


def test_an_abstaining_forecaster_gets_no_trader_decision():
    b = branches.ensure("p0", policies.freeze_blind_forecaster())
    run = runner.run_controlled(Q, [b], sources.ListSource(DOCS), lambda proto: (lambda task, role: (SimpleNamespace(probability="n/a", rationale="", cited=[]), 0.0)))[0]
    assert run.p is None and decision.replay(Q, controls.freeze_trader(), run, trader("buy_yes")) is None
