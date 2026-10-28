"""Forecast feedback and the activity floor: top-up, scoring, floor enforcement and tagging, guard compliance, the published contract. Stubbed models."""

from __future__ import annotations

import pytest
from test_markets_day import NOW, WORLD, Script, _store, fake_get  # noqa: F401  (autouse fixture re-exported so it applies here)

from algent_backend.markets import bot_forecasts, book, day, day_report, day_tools, flags, guards, score, store, strategies
from algent_backend.markets.contracts import BotForecast, Market
from algent_backend.markets.day_prompt import Call, ForecastOut, Turn


@pytest.fixture(autouse=True)
def _feedback_on(monkeypatch, _store):                                # after the store fixture, which zeroes the quota for the older tests
    monkeypatch.setattr(flags, "FORECASTS_PER_RUN", 2)


@pytest.fixture
def floor(monkeypatch):
    monkeypatch.setattr(flags, "MIN_EXPOSURE_PCT", 0.02)              # $200 of the $10k bankroll
    monkeypatch.setattr(flags, "MUST_TRADE_MIN_EXPOSURE_PCT", 0.02)


def fc(mid, pct, reason="Reads that way."):
    return ForecastOut(market=mid, p_pct=pct, confidence="medium", reason=reason)


def go(sid, turns, **kw):
    return day.run(strategy_id=sid, ask=Script(turns), now=NOW, get=fake_get(), corpus=None, **kw)


def buy(mid="a1", usd=100.0, p=0.7, **kw):
    return Call(tool="buy", market=mid, side="yes", usd=usd, p_yes=p, **{"reason": "Talks are on.", **kw})


# ── forecasts ────────────────────────────────────────────────────────────────────────────────────
def test_a_short_run_is_sent_back_to_forecast_then_recorded():
    s = Script([Turn(calls=[Call(tool="search_markets", query="ceasefire")], forecasts=[fc("a1", 70)]), Turn(done=True),
                Turn(forecasts=[fc("a2", 25)]), Turn(done=True, summary="forecast only")])
    rep = day.run(strategy_id="base-rate", ask=s, now=NOW, get=fake_get(), corpus=None)
    assert "STILL OWE 1 MORE FORECAST" in s.tasks[1] and "FORECASTS OWED" in s.tasks[2]
    assert rep["forecasts"] == 2 and rep["orders"] == 0 and rep["stopped"] == "done"
    rows = {f.market_id: f for f in store.bot_forecasts("base-rate")}
    assert set(rows) == {"a1", "a2"} and rows["a1"].p == 0.7 and rows["a2"].p == 0.25
    assert rows["a1"].market == pytest.approx(0.5) and rows["a2"].market == pytest.approx(0.2) and rows["a1"].strategy == "base-rate"
    assert store.day_runs("base-rate")[0].forecasts == 2 and store.bot_forecasts("delineation") == []          # per strategy, nobody else's


def test_the_top_up_is_bounded_and_a_short_run_is_recorded_short(monkeypatch):
    monkeypatch.setattr(flags, "FORECASTS_PER_RUN", 5)
    s = Script([Turn(forecasts=[fc("a1", 60)]), Turn(done=True)] + [Turn(done=True)] * 8)
    rep = day.run(strategy_id="base-rate", ask=s, now=NOW, get=fake_get(), corpus=None)
    assert rep["forecasts"] == 1 and rep["turns"] == 2 + flags.FORECAST_PUSHES
    assert rep["stopped"] == "done"                                                                      # never loops forever, never fabricates one


def test_percent_and_fraction_inputs_unknown_markets_and_bounds():
    ss = day_tools.Session(now=NOW, get=fake_get(), strategy=strategies.get("base-rate"))
    msg = ss.forecasts([fc("a1", 0.3), fc("a2", 99.9), fc("nope", 50), fc("a1", 0)])
    assert "skipped" in msg and "nope" in msg
    assert ss.forecast_log["a1"].p == 0.3 or ss.forecast_log["a1"].p == flags.P_MIN                       # the later 0 was refused, the 0.3 fraction kept
    assert ss.forecast_log["a2"].p == flags.P_MAX                                                          # never certainty


def test_an_order_carries_the_agents_probability_as_a_forecast_too():
    rep = go("delineation", [Turn(calls=[buy("a1", p=0.7)], forecasts=[fc("a2", 20)]), Turn(done=True)])
    assert {f.market_id for f in store.bot_forecasts("delineation")} == {"a1", "a2"} and rep["forecasts"] == 2


def test_forecasts_are_scored_on_resolution_against_outcome_and_market(monkeypatch):
    base = dict(strategy="base-rate", run_id="r", day="2026-10-24")
    store.append_bot_forecasts([BotForecast(id="1", market_id="m1", at="2026-10-24T10:00:00+00:00", p=0.8, market=0.5, **base),
                                BotForecast(id="2", market_id="m2", at="2026-10-24T10:00:01+00:00", p=0.2, market=0.4, **base),
                                BotForecast(id="3", market_id="m3", at="2026-10-24T10:00:02+00:00", p=0.9, market=0.9, **base)])
    store.save_markets([Market(id="m1", question="q1", status="resolved", outcome="yes"), Market(id="m2", question="q2", status="resolved", outcome="no"),
                        Market(id="m3", question="q3")])
    monkeypatch.setattr(flags, "FORECAST_MIN_RESOLVED", 3)
    early = bot_forecasts.summary("base-rate")
    assert early["made"] == 3 and early["resolved"] == 2 and early["shown"] is False and early["brier"] is None     # "n=2, too early"
    monkeypatch.setattr(flags, "FORECAST_MIN_RESOLVED", 2)
    s = bot_forecasts.summary("base-rate")
    assert s["shown"] and s["brier"] == pytest.approx((0.2**2 + 0.2**2) / 2, abs=1e-4)
    assert s["brier_market"] == pytest.approx((0.5**2 + 0.4**2) / 2, abs=1e-4) and s["skill_vs_market"] > 0
    assert s["log_loss"] == pytest.approx(-(__import__("math").log(0.8) + __import__("math").log(0.8)) / 2, abs=1e-3)
    rec = {r["market_id"]: r for r in s["recent"]}
    assert rec["m1"]["outcome"] == "yes" and rec["m3"]["outcome"] == "" and rec["m1"]["market"] == 0.5 and rec["m2"]["question"] == "q2"


# ── the activity floor ───────────────────────────────────────────────────────────────────────────
def test_the_floor_is_told_to_the_agent_and_enforced_with_a_push(floor):
    s = Script([Turn(calls=[Call(tool="search_markets", query="ceasefire")], forecasts=[fc("a1", 70), fc("a2", 20)]), Turn(done=True),
                Turn(calls=[buy("a1", usd=300, p=0.8)]), Turn(done=True)])
    rep = day.run(strategy_id="base-rate", ask=s, now=NOW, get=fake_get(), corpus=None)
    assert "UNDER YOUR 2% ACTIVITY FLOOR" in s.tasks[1] and "activity floor 2% of the bankroll - YOU ARE $200.00 UNDER IT" in s.tasks[0]
    assert rep["filled"] == 1 and rep["exposure_pct"] >= 0.02 and store.day_runs("base-rate")[0].exposure_pct >= 0.02


def test_no_edge_floor_buys_are_tagged_small_and_chosen_ones_are_not(floor):
    ss = day_tools.Session(now=NOW, get=fake_get(), strategy=strategies.get("base-rate"))
    ss.run(1, Call(tool="market", market="a1"))
    assert "floor" in ss.t_portfolio()[0]
    ss.run(1, buy("a1", usd=400, p=0.5))                               # no edge, under the floor: a minimum-ticket floor position, not 400
    d = store.decisions("base-rate")[-1]
    assert d.tag == "floor" and -d.cash_flow == pytest.approx(flags.TRADE_MIN_TICKET) and any("floor position" in c for c in d.clips)
    assert -d.cash_flow < 400
    ss.run(1, Call(tool="buy", market="a2", side="yes", usd=250, p_yes=0.5, reason="The Fed is boxed in."))   # 30 points of edge: chosen
    d2 = store.decisions("base-rate")[-1]
    assert d2.tag == "" and -d2.cash_flow == pytest.approx(250)
    assert guards.floor_stake(0.0, "yes", 0.5, 10000) == flags.TRADE_MIN_TICKET and guards.floor_stake(0.7, "yes", 0.5, 10000) > flags.TRADE_MIN_TICKET


def test_an_agent_declared_floor_buy_is_tagged_only_while_under_the_floor(floor):
    ss = day_tools.Session(now=NOW, get=fake_get(), strategy=strategies.get("base-rate"))
    ss.run(1, buy("a1", usd=300, p=0.9, floor=True))
    assert store.decisions("base-rate")[-1].tag == "floor"
    ss.run(1, buy("a2", usd=100, p=0.9, floor=True))                   # exposure is now over the floor: the flag does not tag a chosen position
    assert store.decisions("base-rate")[-1].tag == ""


def test_floor_positions_obey_the_guards_cash_and_caps(monkeypatch):
    monkeypatch.setattr(flags, "MIN_EXPOSURE_PCT", 0.9)               # a floor above the exposure cap is clamped, never reached by breaking the guards
    st = strategies.get("base-rate")
    assert st.floor_pct == pytest.approx(st.exposure_frac * flags.FLOOR_CAP_SHARE) and st.floor_pct < 0.9
    monkeypatch.setattr(flags, "STRAT_MAX_ORDERS_PER_RUN", 30)
    ss = day_tools.Session(now=NOW, get=fake_get(), strategy=strategies.get("base-rate"))
    for _ in range(4):
        ss.run(1, buy("a1", usd=5000, p=0.99, floor=True))
        ss.run(1, buy("a2", usd=5000, p=0.99, floor=True))
    ds = store.decisions("base-rate")
    for mid in ("a1", "a2"):
        assert sum(-d.cash_flow for d in ds if d.market_id == mid) <= st.position_frac * st.bankroll + 0.01
    assert book.cash(ds) >= 0 and sum(h.cost for h in book.holdings(ds).values()) <= st.exposure_frac * st.bankroll + 0.01


def test_must_trade_bots_get_the_higher_floor_and_the_roster_validates(monkeypatch):
    monkeypatch.setattr(flags, "MIN_EXPOSURE_PCT", 0.30)
    monkeypatch.setattr(flags, "MUST_TRADE_MIN_EXPOSURE_PCT", 0.60)
    assert strategies.get("base-rate").min_exposure_pct == 0.30 and strategies.get("baseline-must-trade").min_exposure_pct == 0.60
    assert strategies.get("day").min_exposure_pct == 0.30 and strategies.validate() == []
    assert strategies.get("baseline-must-trade").floor_pct == pytest.approx(0.45)


# ── the published contract ───────────────────────────────────────────────────────────────────────
def test_the_track_record_publishes_forecasts_exposure_and_floor_additively(floor):
    from algent_backend.contracts import shapes, spec

    go("base-rate", [Turn(calls=[buy("a1", usd=400, p=0.52)], forecasts=[fc("a2", 20)]), Turn(done=True)])
    doc = score.track_record()
    r = {x["id"]: x for x in doc["strategies"]}["base-rate"]
    assert r["forecasts"]["made"] == 2 and r["forecasts"]["shown"] is False and r["forecasts"]["brier"] is None and r["forecasts"]["min_resolved"] == flags.FORECAST_MIN_RESOLVED
    assert {x["market_id"] for x in r["forecasts"]["recent"]} == {"a1", "a2"} and r["exposure"]["floor_pct"] == pytest.approx(0.02) and r["exposure"]["pct"] > 0
    assert r["floor"]["opened"] == 1 and [g["label"] for g in r["floor"]["groups"]] == ["floor (no edge)", "chosen"]
    assert r["log"][0]["tag"] == "floor" and r["runs"][0]["forecasts"] == 2
    assert spec.validate(doc, shapes.SHAPES["ohmega.track-record"]) == []
    assert day_report.section(None, "delineation")["forecasts"]["made"] == 0                            # a bot that has not run: zeros, not missing
