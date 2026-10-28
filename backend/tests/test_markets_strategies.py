"""The strategy roster: validation, the lab methods, independence, must-trade, caps, isolated books, the schedule and the published contract. All with stubbed models."""

from __future__ import annotations

import argparse
import inspect
import json
from datetime import UTC, datetime, timedelta

import pytest
from test_markets_day import NOW, WORLD, Script, _store, fake_get  # noqa: F401  (the fixture is autouse in its module; re-exported so it applies here)

from algent_backend.markets import book, day, day_prompt, day_report, day_tools, flags, methods, score, store, strategies
from algent_backend.markets.contracts import Decision, DayRun, Snapshot
from algent_backend.markets.day_prompt import Call, Turn

INDEPENDENT = ["base-rate", "delineation", "delineation-base-rate", "baseline-must-trade", "delineation-must-trade"]


def buy(mid="a1", usd=100.0, p=0.7, **kw):
    return Call(tool="buy", market=mid, side="yes", usd=usd, p_yes=p, **{"reason": "Talks are on.", **kw})


def trade_run(sid, turns, **kw):
    return day.run(strategy_id=sid, ask=Script(turns), now=NOW, get=fake_get(), corpus=None, **kw)


# ── the roster ───────────────────────────────────────────────────────────────────────────────────
def test_the_roster_is_valid_and_names_lab_minds():
    from algent_backend.experiment import qset

    rows = strategies.roster()
    assert strategies.validate(rows) == []
    assert strategies.ids() == ["day", "daily", "fast", *INDEPENDENT]
    assert all(s.method in qset.NAMED for s in rows)                         # the lab's ids stay the source of truth
    assert {s.method for s in rows} == set(methods.NAMES) == {"p0b", "p0b+prior", "b", "b+prior"}
    must = {s.id: s.min_orders for s in rows if s.must_trade}
    assert must == {"baseline-must-trade": 2, "delineation-must-trade": 1}
    assert all(s.horizon_h == 168 for s in rows if s.id in INDEPENDENT) and strategies.get("day").horizon_h == flags.DAY_HORIZON_H


def test_validation_catches_a_broken_roster():
    good = strategies.get("base-rate")
    from dataclasses import replace

    bad = [good, replace(good), replace(good, id="x", method="nope"), replace(good, id="y", must_trade=True, min_orders=0), replace(good, id="z", run_hours=())]
    problems = " | ".join(strategies.validate(bad))
    for needle in ("duplicate id", "not a lab mind id", "must_trade needs", "bad run times"):
        assert needle in problems


def test_methods_inject_the_labs_own_instructions_and_fields():
    from algent_backend.experiment import minds

    assert methods.section("p0b") == "" and day_prompt.role(strategies.get("day")) == day_prompt.role()           # the day book's text is unchanged
    prior = day_prompt.role(strategies.get("base-rate"))
    assert minds.PRIOR_ADDENDUM in prior and "reference_class" in prior and "base_rate_pct" in prior
    delin = day_prompt.role(strategies.get("delineation"))
    assert minds.DELINEATION_ADDENDUM in delin and "possibilities" in delin and minds.PRIOR_ADDENDUM not in delin
    both = day_prompt.role(strategies.get("delineation-base-rate"))
    assert minds.DELINEATION_ADDENDUM + minds.PRIOR_ADDENDUM in both
    assert "YOU MUST TRADE" in day_prompt.role(strategies.get("baseline-must-trade")) and "YOU MUST TRADE" not in prior
    assert "168 hours" in prior and "seven days" not in prior and "7 days" in prior


# ── independence and isolated books ───────────────────────────────────────────────────────────────
def test_a_strategy_never_reads_another_ones_forecasts_or_desk_forecasts():
    for mod in (day, day_tools, day_prompt, methods, strategies):                  # the code path cannot reach a forecast store
        src = inspect.getsource(mod)
        assert "store.forecasts" not in src and "latest_forecasts" not in src and "paper." not in src
    # the day book trades and writes a distinctive reason; the base-rate bot's whole transcript never contains it
    trade_run("day", [Turn(calls=[buy(reason="ZEBRA-SECRET-DAY-REASON")]), Turn(done=True)])
    a = Script([Turn(calls=[Call(tool="portfolio")]), Turn(done=True, summary="nothing")])
    day.run(strategy_id="base-rate", ask=a, now=NOW, get=fake_get(), corpus=None)
    assert not any("ZEBRA" in t for t in a.tasks)
    assert "no open positions" in a.tasks[0]
    assert store.decisions("base-rate") == [] and len(store.decisions("day")) == 1


def test_books_ledgers_watchlists_and_equity_are_isolated():
    trade_run("base-rate", [Turn(calls=[buy(usd=200), Call(tool="watchlist", action="add", market="a2", reason="wait")]), Turn(done=True)])
    trade_run("delineation", [Turn(calls=[buy("a2", usd=300, basis="possibilities H1 H2")]), Turn(done=True)])
    a, b = store.decisions("base-rate"), store.decisions("delineation")
    assert [d.market_id for d in a] == ["a1"] and [d.market_id for d in b] == ["a2"]
    assert book.cash(a) == pytest.approx(flags.BANKROLL - 200) and book.cash(b) == pytest.approx(flags.BANKROLL - 300)
    assert b[0].basis == "possibilities H1 H2" and a[0].book == "base-rate" and set(store.watchlist("base-rate")) == {"a2"} and store.watchlist("delineation") == {}
    assert {r.strategy for r in store.day_runs()} == {"base-rate", "delineation"} and len(store.day_runs("base-rate")) == 1
    store.append_snapshots([Snapshot(market_id=m, at=NOW.isoformat(), p=0.5) for m in ("a1", "a2")])
    series = {p.book for p in book.mark(NOW)}
    assert {"base-rate", "delineation"} <= series and "day" not in series


def test_the_old_daily_and_fast_books_keep_their_ledgers_and_series():
    assert strategies.get("daily").series == "trader" and strategies.get("fast").series == "fast"
    old = Decision(id="old", market_id="m", at=NOW.isoformat(), day="2026-10-24", action="buy_yes", side="yes", price=0.5, shares=100, cash_flow=-50)
    store.append_decisions([old])                                              # a line written before the roster: book defaults to "daily"
    trade_run("daily", [Turn(calls=[buy(usd=100)]), Turn(done=True)])
    ds = store.decisions("daily")
    assert len(ds) == 2 and ds[0].id == "old" and ds[1].book == "daily"
    assert any(p.book == "trader" for p in book.mark(NOW))


def test_a_seven_day_strategy_sees_markets_the_day_book_cannot():
    far = lambda sid: {v.market.id for v in __import__("algent_backend.markets.browse", fromlist=["x"]).search(  # noqa: E731
        "", now=NOW, get=fake_get(), horizon_h=strategies.get(sid).horizon_h, min_hours=strategies.get(sid).min_hours_left)}
    assert "far" in far("base-rate") and "far" not in far("day")


# ── must trade ───────────────────────────────────────────────────────────────────────────────────
def test_must_trade_sends_a_finished_run_back_to_trade_and_records_met():
    s = Script([Turn(done=True, summary="no edge"), Turn(calls=[buy(usd=10, reason="No real edge; smallest position on my best guess.")]), Turn(done=True, summary="took the smallest")])
    rep = day.run(strategy_id="delineation-must-trade", ask=s, now=NOW, get=fake_get(), corpus=None)
    assert rep["filled"] == 1 and rep["must_trade"] == "met" and rep["turns"] == 3
    assert "MUST STILL FILL 1 MORE ORDER" in s.tasks[1] and store.day_runs("delineation-must-trade")[0].must_trade == "met"


def test_must_trade_records_unmet_instead_of_faking_a_trade():
    rep = day.run(strategy_id="baseline-must-trade", ask=Script([Turn(done=True)] * 6), now=NOW, get=fake_get(), corpus=None)
    assert rep["orders"] == 0 and rep["must_trade"] == "unmet: 0 of 2" and store.decisions("baseline-must-trade") == []
    rep = day.run(strategy_id="baseline-must-trade", ask=Script([Turn(calls=[buy()]), Turn(done=True)] + [Turn(done=True)] * 4), now=NOW + timedelta(minutes=1),
                  get=fake_get(), corpus=None)
    assert rep["must_trade"] == "unmet: 1 of 2"
    assert day.run(strategy_id="base-rate", ask=Script([Turn(done=True)]), now=NOW, get=fake_get(), corpus=None)["must_trade"] == ""      # others owe nothing


def test_a_refused_or_clipped_to_nothing_order_does_not_count_as_filled():
    s = Script([Turn(calls=[Call(tool="buy", market="nope", side="yes", usd=50, reason="x", p_yes=0.6)]), Turn(done=True)] + [Turn(done=True)] * 3)
    rep = day.run(strategy_id="delineation-must-trade", ask=s, now=NOW, get=fake_get(), corpus=None)
    assert rep["must_trade"].startswith("unmet") and rep["filled"] == 0


# ── caps ─────────────────────────────────────────────────────────────────────────────────────────
def test_position_order_and_budget_caps_apply_per_strategy(monkeypatch):
    trade_run("base-rate", [Turn(calls=[buy(usd=5000)]), Turn(done=True)])
    d = store.decisions("base-rate")[0]
    assert -d.cash_flow == pytest.approx(strategies.get("base-rate").position_frac * flags.BANKROLL) and d.clips                      # clipped to 5% and said so
    monkeypatch.setattr(flags, "STRAT_MAX_ORDERS_PER_RUN", 1)
    s = day_tools.Session(now=NOW, get=fake_get(), strategy=strategies.get("delineation"))
    s.run(1, buy("a1"))
    assert "order limit" in s.run(1, buy("a2")).result
    store.append_day_run(DayRun(id="r1", at=NOW.isoformat(), day=NOW.date().isoformat(), usd=flags.STRAT_MAX_USD_PER_DAY, strategy="delineation-base-rate"))
    rep = day.run(strategy_id="delineation-base-rate", ask=Script([Turn(done=True)]), now=NOW, get=fake_get(), corpus=None)
    assert "day budget reached" in rep["stopped"] and rep["turns"] == 0
    other = day.run(strategy_id="delineation", ask=Script([Turn(done=True)]), now=NOW, get=fake_get(), corpus=None)
    assert other["turns"] == 1                                                                                                  # another strategy's spend is not shared
    one = Script([Turn(calls=[Call(tool="portfolio")])] * 7, usd=0.10)
    rep = day.run(strategy_id="base-rate", ask=one, now=NOW + timedelta(hours=1), get=fake_get(), corpus=None)
    assert rep["stopped"] == "run budget reached" and rep["usd"] <= flags.STRAT_MAX_USD_PER_RUN + 0.10


def test_the_roster_stays_inside_the_spend_target():
    rows = strategies.roster()
    assert sum(s.max_usd_day for s in rows) <= 3.2 and all(s.max_usd_run <= 0.15 for s in rows)


# ── the schedule ─────────────────────────────────────────────────────────────────────────────────
def test_every_strategy_has_a_staggered_job_off_the_crunch():
    from algent_backend.ops.jobq.capacity import daily_starts
    from algent_backend.ops.products import validate, views

    slots = []
    for s in strategies.roster():
        job = views.job(f"markets-{s.id}")[1]
        assert job.spend in ("capped", "paid") and daily_starts(job.when()) == [h * 60 + s.run_minute for h in s.run_hours] or s.id in ("daily", "fast")
        slots += [(s.id, m) for m in daily_starts(job.when())]
        assert not any(5 * 60 <= m < 7 * 60 for _, m in slots if _ == s.id and s.id != "daily")
    indep = [(i, m) for i, m in slots if i in INDEPENDENT or i == "day"]
    for i, (a, ma) in enumerate(indep):
        for b, mb in indep[i + 1:]:
            assert abs(ma - mb) >= 10, (a, b)
    assert validate.validate() == []
    assert views.job("markets-delineation")[1].argv == ("markets", "strategy", "delineation")


def test_next_run_is_the_next_slot():
    s = strategies.get("base-rate")
    assert strategies.next_run(s, datetime(2026, 10, 24, 9, 6, tzinfo=UTC)) == datetime(2026, 10, 24, 13, 5, tzinfo=UTC)
    assert strategies.next_run(s, datetime(2026, 10, 24, 21, 6, tzinfo=UTC)) == datetime(2026, 10, 25, 9, 5, tzinfo=UTC)


# ── no desk forecast anywhere; the CLI ───────────────────────────────────────────────────────────
def test_the_scheduled_daily_runs_the_daily_strategy_and_never_the_desk_forecast(monkeypatch, capsys):
    from algent_backend.cli.newsroom import markets as cli
    from algent_backend.markets import forecast, mirror, publish

    monkeypatch.setattr(mirror, "refresh", lambda: {})
    monkeypatch.setattr(publish, "publish", lambda: {"ok": True})
    monkeypatch.setattr(forecast, "run", lambda **k: (_ for _ in ()).throw(AssertionError("the desk forecast pass must not run")))
    seen = []
    monkeypatch.setattr(day, "run", lambda **k: seen.append(k["strategy_id"]) or {"orders": 0})
    assert cli.run_daily(argparse.Namespace(no_trade=False)) == 0
    out = json.loads(capsys.readouterr().out)
    assert seen == ["daily"] and "forecast" not in out and "publish" in out
    cli.run_strategy(argparse.Namespace(id="", list=True, dry_run=False))
    assert [r["id"] for r in json.loads(capsys.readouterr().out)] == strategies.ids()


def test_the_rule_book_is_retired_and_opens_nothing():
    from algent_backend.markets import paper

    assert flags.RULE_BOOK_ENABLED is False
    assert paper.run(now=NOW)["opened"] == 0


# ── the published contract ───────────────────────────────────────────────────────────────────────
def test_the_track_record_carries_one_section_per_strategy_additively():
    from algent_backend.contracts import shapes, spec

    trade_run("base-rate", [Turn(calls=[buy(usd=200)]), Turn(done=True)])
    doc = score.track_record()
    rows = {r["id"]: r for r in doc["strategies"]}
    assert list(rows) == strategies.ids()
    r = rows["base-rate"]
    assert r["method"] == "p0b+prior" and r["method_name"] == "Base rate first" and r["next_run"] and r["style"] and r["run_hours"] == [9, 13, 17, 21]
    assert r["summary"]["open"] == 1 and r["open_positions"][0]["market_id"] == "a1" and r["log"][0]["action"] == "buy_yes" and r["log"][0]["rationale"]
    assert rows["baseline-must-trade"]["must_trade"] is True and rows["baseline-must-trade"]["min_orders"] == 2
    assert "trader" in doc and "fast" in doc and "day" in doc                                    # the older objects are untouched
    assert spec.validate(doc, shapes.SHAPES["ohmega.track-record"]) == []
    assert day_report.section(None, "base-rate")["summary"]["open"] == 1
