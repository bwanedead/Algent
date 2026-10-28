"""The trader: mechanical guards (clipping, cash, exposure, sides), the immutable decision ledger, settlement, the shared equity marks and the CLI daily wiring."""

from __future__ import annotations

import argparse
import json
from datetime import UTC, datetime, timedelta
from types import SimpleNamespace

import pytest

from algent_backend.markets import book, flags, guards, store, trader, trader_report
from algent_backend.markets.book import Holding
from algent_backend.markets.contracts import Forecast, Market, Snapshot

NOW = datetime(2026, 10, 17, 12, 0, tzinfo=UTC)


@pytest.fixture(autouse=True)
def _store(tmp_path, monkeypatch):
    for env, name in (("ALGENT_MARKETS_STORE", "ms"), ("ALGENT_CALENDAR_STORE", "cal"), ("ALGENT_STATEMENTS_STORE", "st"), ("ALGENT_SANCTIONS_STORE", "sx"),
                      ("ALGENT_INTEL_STORE", "intel"), ("ALGENT_GEOLEDGER_STORE", "geo"), ("ALGENT_PROFILE_STORE", "prof"), ("ALGENT_RETRIEVAL_STORE", "ret")):
        monkeypatch.setenv(env, str(tmp_path / name))
    monkeypatch.delenv("DATABASE_URL", raising=False)


def seed(mid="m1", price=0.30, ours=0.60, end_days=60, base=NOW):
    store.save_markets([Market(id=mid, question=f"Will thing {mid} happen?", description="Resolves YES if it does.", url=f"https://polymarket.com/event/{mid}",
                               end_date=(base + timedelta(days=end_days)).isoformat(), volume=1e5, theaters=[], countries=[])])
    store.append_snapshots([Snapshot(market_id=mid, at=(base - timedelta(hours=2)).isoformat(), p=price)])
    if ours is not None:
        store.append_forecast(Forecast(id=f"fc-{mid}", market_id=mid, made_at=(base - timedelta(days=1)).isoformat(), p=ours, rationale="Base rate is low."))


class Agent:
    """A stub model: answers each market label with a scripted (action, stake); anything unscripted is a hold."""

    def __init__(self, script=None, usd=0.04):
        self.script, self.usd, self.tasks = script or {}, usd, []

    def __call__(self, task, role=""):
        self.tasks.append(task)
        labels = [line.split()[1] for line in task.splitlines() if line.startswith("### ")]
        decisions = []
        for lab in labels:
            action, stake = self.script.get(lab, ("hold", 0.0))
            decisions.append(SimpleNamespace(market=lab, action=action, stake_usd=stake, rationale=f"Because {lab}."))
        return SimpleNamespace(decisions=decisions), self.usd


# ── guards ───────────────────────────────────────────────────────────────────────────────────────
def test_a_buy_is_clipped_to_the_position_limit_and_the_cut_is_recorded():
    f = guards.apply("buy_yes", 5000, held=None, yes_price=0.30, cash=10000, exposure=0, tradable=True)
    assert f.action == "buy_yes" and -f.cash_flow == flags.MAX_POSITION_FRAC * flags.BANKROLL
    assert f.price == pytest.approx(0.31) and f.shares == pytest.approx(500 / 0.31, rel=1e-3)
    assert any("position limit" in c for c in f.clips)


def test_a_buy_cannot_spend_cash_the_book_does_not_have_or_pass_the_exposure_cap():
    f = guards.apply("buy_yes", 400, held=None, yes_price=0.5, cash=120, exposure=0, tradable=True)
    assert -f.cash_flow == 120 and any("cash" in c for c in f.clips)
    f = guards.apply("buy_no", 400, held=None, yes_price=0.5, cash=9000, exposure=flags.MAX_EXPOSURE_FRAC * flags.BANKROLL - 60, tradable=True)
    assert -f.cash_flow == 60 and f.side == "no" and any("exposure" in c for c in f.clips)
    f = guards.apply("buy_yes", 400, held=None, yes_price=0.5, cash=-5, exposure=0, tradable=True)
    assert f.action == "hold" and f.cash_flow == 0                       # cash can never go negative


def test_adds_count_toward_the_position_limit_and_the_other_side_is_refused():
    h = Holding("m", "yes", 1000, 495.0, "2026-10-01T00:00:00+00:00", 0.495)
    f = guards.apply("buy_yes", 300, held=h, yes_price=0.5, cash=9000, exposure=450, tradable=True)
    assert f.action == "hold" and any("below the" in c for c in f.clips)       # only 50 of room left: under the minimum ticket
    f = guards.apply("buy_no", 100, held=h, yes_price=0.5, cash=9000, exposure=450, tradable=True)
    assert f.action == "hold" and any("sell it before buying NO" in c for c in f.clips)


def test_no_shorting_unpriced_or_closed_markets_and_dust():
    assert guards.apply("sell", 100, held=None, yes_price=0.5, cash=1e4, exposure=0, tradable=True).clips == ["no position to sell: held"]
    assert guards.apply("buy_yes", 100, held=None, yes_price=None, cash=1e4, exposure=0, tradable=True).action == "hold"
    assert guards.apply("buy_yes", 100, held=None, yes_price=0.5, cash=1e4, exposure=0, tradable=False).action == "hold"
    f = guards.apply("buy_yes", 3, held=None, yes_price=0.5, cash=1e4, exposure=0, tradable=True)
    assert f.action == "hold" and f.cash_flow == 0
    assert guards.apply("do_a_dance", 100, held=None, yes_price=0.5, cash=1e4, exposure=0, tradable=True).action == "hold"


def test_a_sell_never_exceeds_the_position_and_pays_slippage():
    h = Holding("m", "yes", 100, 40.0, "2026-10-01T00:00:00+00:00", 0.40)
    f = guards.apply("sell", 10_000, held=h, yes_price=0.60, cash=0, exposure=40, tradable=True)
    assert f.action == "sell" and f.shares == 100 and f.price == pytest.approx(0.59) and f.cash_flow == pytest.approx(59.0) and f.realised == pytest.approx(19.0)
    part = guards.apply("sell", 20, held=h, yes_price=0.60, cash=0, exposure=40, tradable=True)
    assert part.shares == pytest.approx(20 / 0.59, rel=1e-3) and part.realised == pytest.approx(part.cash_flow - 40 * part.shares / 100, abs=0.01)
    whole = guards.apply("sell", 0, held=h, yes_price=0.60, cash=0, exposure=40, tradable=True)
    assert whole.shares == 100 and any("no size" in c for c in whole.clips)


# ── the pass ─────────────────────────────────────────────────────────────────────────────────────
def test_the_pass_fills_through_the_guards_and_records_every_decision_including_holds():
    seed("a", price=0.30, ours=0.60)
    seed("b", price=0.50, ours=0.52)
    agent = Agent({"M1": ("buy_yes", 5000)})
    out = trader.run(ask=agent, now=NOW, record={}, index=None)
    ds = store.decisions()
    assert out["decided"] == 2 and out["filled"] == 1 and out["clipped"] == 1 and out["usd"] == 0.04
    buy = next(d for d in ds if d.action == "buy_yes")
    assert buy.market_id == "a" and -buy.cash_flow == 500 and buy.requested == 5000 and buy.clips and buy.ours == 0.60 and buy.market == 0.30
    hold = next(d for d in ds if d.action == "hold")
    assert hold.rationale.startswith("Because") and hold.cash_flow == 0 and hold.day == "2026-10-17"
    assert book.cash(ds) == flags.BANKROLL - 500 and set(book.holdings(ds)) == {"a"}
    task = agent.tasks[0]
    assert "Will thing a happen?" in task and "Resolves YES if it does." in task and "YES 30%" in task and "60%" in task and "Base rate is low." in task


def test_an_unanswered_market_is_a_clipped_hold_and_an_unknown_label_is_ignored():
    seed("a")
    trader.run(ask=lambda task, role="": (SimpleNamespace(decisions=[SimpleNamespace(market="M9", action="buy_yes", stake_usd=400, rationale="x")]), 0.01),
               now=NOW, record={}, index=None)
    d = store.decisions()[0]
    assert d.action == "hold" and any("no decision" in c for c in d.clips)


def test_a_rerun_the_same_day_asks_nothing_and_the_ledger_only_grows():
    seed("a")
    trader.run(ask=Agent({"M1": ("buy_yes", 100)}), now=NOW, record={}, index=None)
    path = store.root() / "decisions.jsonl"
    before = path.read_bytes()
    again = Agent()
    out = trader.run(ask=again, now=NOW + timedelta(hours=1), record={}, index=None)
    assert again.tasks == [] and out["decided"] == 0
    assert path.read_bytes() == before                                    # nothing rewritten, nothing appended
    # the next day, a new line is APPENDED after the old bytes
    trader.run(ask=Agent(), now=NOW + timedelta(days=1), record={}, index=None)
    assert path.read_bytes().startswith(before) and len(store.decisions()) == 2


def test_the_day_budget_stops_the_pass_between_batches(monkeypatch):
    monkeypatch.setattr(flags, "TRADE_BATCH", 1)
    monkeypatch.setattr(flags, "TRADE_MAX_USD_PER_DAY", 0.05)
    for i in range(4):
        seed(f"m{i}", ours=0.5 + 0.1 * i)
    out = trader.run(ask=Agent(usd=0.04), now=NOW, record={}, index=None)
    assert out["decided"] == 2 and "day budget" in out["stopped"]


def test_a_refused_call_ends_the_pass_without_a_line():
    class BudgetRefusedError(Exception):
        pass

    def refuse(task, role=""):
        raise BudgetRefusedError("halt")

    seed("a")
    out = trader.run(ask=refuse, now=NOW, record={}, index=None)
    assert out["failed"] == 1 and "budget gate" in out["stopped"] and store.decisions() == []


def test_held_markets_are_offered_first_even_without_a_current_forecast():
    seed("wide", price=0.30, ours=0.90)                                                  # the widest gap: M1 on day one
    seed("h", price=0.30, ours=0.60)                                                     # M2 on day one: bought
    trader.run(ask=Agent({"M2": ("buy_yes", 100)}), now=NOW, record={}, index=None)
    store.append_snapshots([Snapshot(market_id=m, at=(NOW + timedelta(days=1)).isoformat(), p=0.35) for m in ("wide", "h")])
    agent = Agent()
    trader.run(ask=agent, now=NOW + timedelta(days=1, hours=1), record={}, index=None)
    task = agent.tasks[0]
    assert "### M1  Will thing h happen?" in task and "YOU HOLD: YES" in task and "### M2  Will thing wide happen?" in task


# ── settlement, marks, report ────────────────────────────────────────────────────────────────────
def test_a_resolved_position_settles_through_the_shared_payout():
    seed("a", price=0.30, ours=0.60)
    trader.run(ask=Agent({"M1": ("buy_yes", 200)}), now=NOW, record={}, index=None)
    m = store.markets()["a"]
    store.save_markets([m.model_copy(update={"status": "resolved", "outcome": "yes", "resolved_at": "2026-10-20"})])
    assert trader.settle(NOW + timedelta(days=3)) == 1
    assert trader.settle(NOW + timedelta(days=3)) == 0                                  # once
    ds = store.decisions()
    s = ds[-1]
    assert s.action == "settle" and s.cash_flow == pytest.approx(200 / 0.31, abs=0.01) and s.realised == pytest.approx(s.cash_flow - 200, abs=0.01)
    assert book.holdings(ds) == {} and book.cash(ds) == pytest.approx(flags.BANKROLL + s.realised, abs=0.01)
    assert book.payout("void", "yes") == 0.5 and book.payout("no", "yes") == 0.0


def test_marks_write_one_point_per_book_per_day_and_the_two_books_are_valued_alike():
    seed("a", price=0.30, ours=0.60)
    from algent_backend.markets import paper

    paper.run(now=NOW)                                                                   # the rule book opens its edge-rule position
    trader.run(ask=Agent({"M1": ("buy_yes", 200)}), now=NOW, record={}, index=None)
    pts = book.mark(NOW)
    assert {p.book for p in pts} == {"trader", "rule"}
    t = next(p for p in pts if p.book == "trader")
    assert t.cash == flags.BANKROLL - 200 and t.n_open == 1 and t.equity == pytest.approx(t.cash + t.holdings)
    assert book.mark(NOW + timedelta(hours=3)) == []                                     # same day: left as first written
    assert len(store.equity_points()) == 2
    assert [c["flat"] for c in trader_report.curve()] == [flags.BANKROLL]


def test_the_report_lists_positions_with_the_agents_words_and_the_log_with_outcomes():
    seed("a", price=0.30, ours=0.60)
    trader.run(ask=Agent({"M1": ("buy_yes", 200)}), now=NOW, record={}, index=None)
    book.mark(NOW)
    sec = trader_report.section("2026-10-17")
    pos = sec["open_positions"][0]
    assert pos["side"] == "yes" and pos["rationale"] == "Because M1." and pos["cost"] == 200 and sec["today"]["bought"] == 1
    assert sec["log"][0]["action"] == "buy_yes" and sec["log"][0]["result"] == ""
    store.save_markets([store.markets()["a"].model_copy(update={"status": "resolved", "outcome": "no"})])
    trader.settle(NOW + timedelta(days=1))
    log = trader_report.section()["log"]
    assert log[0]["action"] == "settle" and log[0]["pnl"] == pytest.approx(-200) and log[1]["result"] == "lost"
    assert trader_report.section()["summary"]["losses"] == 1


# ── CLI wiring ───────────────────────────────────────────────────────────────────────────────────
def test_the_published_document_carries_the_trader_section():
    seed("a", price=0.30, ours=0.60)
    trader.run(ask=Agent({"M1": ("buy_yes", 200)}), now=NOW, record={}, index=None)
    book.mark(NOW)
    from algent_backend.markets import score

    doc = score.track_record()
    assert doc["schema"] == "ohmega.track-record/2" and doc["trader"]["summary"]["open"] == 1 and doc["trader"]["curve"][0]["trader"] is not None
