"""Paper portfolio and scoring: sizing math, open/mark/settle lifecycle, Brier/log loss vs market on the same instants, calibration, honesty."""

from __future__ import annotations

import math
from datetime import UTC, datetime, timedelta

import pytest

from algent_backend.markets import flags, paper, score, store
from algent_backend.markets.contracts import Forecast, Market, Snapshot

T0 = datetime(2026, 10, 1, 12, 0, tzinfo=UTC)


@pytest.fixture(autouse=True)
def _store(tmp_path, monkeypatch):
    monkeypatch.setenv("ALGENT_MARKETS_STORE", str(tmp_path / "ms"))
    from algent_backend.markets import flags as mflags

    monkeypatch.setattr(mflags, "RULE_BOOK_ENABLED", True)        # these tests exercise the rule engine itself; in production it is retired


def iso(d):
    return d.isoformat(timespec="seconds")


def market(mid, status="open", outcome="", resolved=None, end_days=30):
    return Market(id=mid, question=f"Will {mid} happen?", url=f"https://polymarket.com/event/{mid}", end_date=iso(T0 + timedelta(days=end_days)),
                  status=status, outcome=outcome, resolved_at=iso(resolved) if resolved else "")


def snap(mid, p, at):
    return Snapshot(market_id=mid, at=iso(at), p=p)


def fc(mid, p, at=T0):
    return Forecast(id=f"fc-{mid}-{iso(at)}", market_id=mid, made_at=iso(at), p=p, rationale="r")


def test_brier_and_log_loss_values():
    assert score.brier(0.8, 1) == pytest.approx(0.04) and score.brier(0.8, 0) == pytest.approx(0.64)
    assert score.log_loss(0.8, 1) == pytest.approx(-math.log(0.8))
    assert score.log_loss(0.0, 1) == pytest.approx(-math.log(0.001))                      # clipped, never infinite


def test_kelly_sizing_is_fractional_capped_and_zero_without_edge():
    assert paper.kelly_stake(0.5, 0.5) == 0.0 and paper.kelly_stake(0.4, 0.5) == 0.0
    # q=0.8 at cost 0.5: full Kelly 0.6 -> quarter 0.15 -> capped at 5% of the bankroll
    assert paper.kelly_stake(0.8, 0.5) == flags.MAX_POSITION_FRAC * flags.BANKROLL
    # small edge stays below the cap: q=0.62, c=0.5 -> full 0.24 -> quarter 0.06 -> cap 0.05 ... use q=0.56: full 0.12 -> 0.03
    assert paper.kelly_stake(0.56, 0.5) == pytest.approx(0.03 * flags.BANKROLL)


def test_open_mark_settle_lifecycle_yes_and_no_sides():
    store.save_markets([market("a"), market("b"), market("c")])
    store.append_snapshots([snap("a", 0.20, T0), snap("b", 0.70, T0), snap("c", 0.50, T0)])
    store.append_forecast(fc("a", 0.45))          # we are above the market: buy YES
    store.append_forecast(fc("b", 0.40))          # below: buy NO
    store.append_forecast(fc("c", 0.55))          # inside the edge threshold: no trade
    out = paper.run(now=T0 + timedelta(minutes=5))
    assert out["opened"] == 2
    pos = paper.positions()
    assert set(pos) == {"a", "b"} and pos["a"].side == "yes" and pos["b"].side == "no"
    assert pos["a"].price == pytest.approx(0.21) and pos["b"].price == pytest.approx(0.31)         # quote of the side + slippage
    assert pos["a"].shares == pytest.approx(pos["a"].stake / 0.21, rel=1e-3)
    assert paper.run(now=T0 + timedelta(minutes=10))["opened"] == 0                               # never added to
    # next day: the market moves in our favour on a; mark-to-market
    store.append_snapshots([snap("a", 0.40, T0 + timedelta(days=1)), snap("b", 0.70, T0 + timedelta(days=1))])
    m = paper.run(now=T0 + timedelta(days=1, hours=1))
    assert m["marked"] == 2 and paper.run(now=T0 + timedelta(days=1, hours=2))["marked"] == 0     # once per day
    a = paper.positions()["a"]
    assert a.value == pytest.approx(a.shares * 0.40, abs=0.01) and a.pnl > 0
    # resolution: a -> yes (we win), b -> yes (our NO loses)
    store.save_markets([market("a", "resolved", "yes", T0 + timedelta(days=3)), market("b", "resolved", "yes", T0 + timedelta(days=3))])
    s = paper.run(now=T0 + timedelta(days=4))
    assert s["settled"] == 2
    done = paper.positions()
    assert done["a"].status == "settled" and done["a"].pnl == pytest.approx(done["a"].shares - done["a"].stake, abs=0.01) and done["a"].pnl > 0
    assert done["b"].pnl == pytest.approx(-done["b"].stake)
    sm = paper.summary()
    assert sm["settled"] == 2 and sm["wins"] == 1 and sm["losses"] == 1 and sm["hit_rate"] == 0.5
    assert sm["realised_pnl"] == pytest.approx(done["a"].pnl + done["b"].pnl) and sm["unrealised_pnl"] == 0
    assert paper.run(now=T0 + timedelta(days=5))["settled"] == 0                                   # settles once


def test_void_pays_half_and_exposure_is_capped(monkeypatch):
    store.save_markets([market("v")])
    store.append_snapshots([snap("v", 0.20, T0)])
    store.append_forecast(fc("v", 0.60))
    paper.run(now=T0 + timedelta(minutes=1))
    p = paper.positions()["v"]
    store.save_markets([market("v", "void", "void", T0 + timedelta(days=2))])
    paper.run(now=T0 + timedelta(days=3))
    assert paper.positions()["v"].value == pytest.approx(p.shares * 0.5, abs=0.01)
    monkeypatch.setattr(flags, "MAX_EXPOSURE_FRAC", 0.06)                                         # room for 600 paper dollars: one 500 stake then 100
    for i in range(3):
        store.save_markets([market(f"x{i}")])
        store.append_snapshots([snap(f"x{i}", 0.2, T0 + timedelta(days=4))])
        store.append_forecast(fc(f"x{i}", 0.7, T0 + timedelta(days=4)))
    paper.run(now=T0 + timedelta(days=4, hours=1))
    assert sum(p.stake for p in paper.positions().values() if p.status == "open") <= 0.06 * flags.BANKROLL + 0.01


def test_no_trade_without_a_fresh_price():
    store.save_markets([market("z")])
    store.append_snapshots([snap("z", 0.2, T0 - timedelta(days=5))])
    store.append_forecast(fc("z", 0.9))
    assert paper.run(now=T0)["opened"] == 0


def resolved_book():
    """Four resolved markets with known prices and forecasts at the same instants."""
    spec = [("w", "yes", 0.9, 0.6), ("x", "no", 0.2, 0.5), ("y", "yes", 0.7, 0.9), ("v", "no", 0.1, 0.05)]    # id, outcome, ours, market
    for i, (mid, out, ours, mkt) in enumerate(spec):
        r = T0 + timedelta(days=10 + i)
        store.save_markets([market(mid, "resolved", out, r)])
        store.append_snapshots([snap(mid, mkt, T0 - timedelta(hours=1))])
        store.append_forecast(fc(mid, ours))
    return spec


def test_scores_compare_us_with_the_market_on_the_same_pairs():
    resolved_book()
    sc = score.forecast_scores(score.pairs())
    ours = [(0.9 - 1) ** 2, 0.2 ** 2, (0.7 - 1) ** 2, 0.1 ** 2]
    mkt = [(0.6 - 1) ** 2, 0.5 ** 2, (0.9 - 1) ** 2, 0.05 ** 2]
    assert sc["compared"] == 4 and sc["brier_ours"] == pytest.approx(sum(ours) / 4, abs=1e-4) and sc["brier_market"] == pytest.approx(sum(mkt) / 4, abs=1e-4)
    assert sc["brier_skill"] == pytest.approx(1 - sum(ours) / sum(mkt), abs=1e-3)
    assert "Too early" in sc["verdict"]                                                           # 4 markets is noise, and says so
    assert sc["brier_diff_series"][-1]["n"] == 4 and sc["brier_diff_series"][-1]["diff"] == pytest.approx((sum(ours) - sum(mkt)) / 4, abs=1e-3)
    cal = {b["low"]: b for b in sc["calibration_ours"]}
    assert cal[0.9]["n"] == 1 and cal[0.9]["hit_rate"] == 1.0 and cal[0.1]["hit_rate"] == 0.0


def test_verdict_after_enough_markets_and_losses_are_stated(monkeypatch):
    monkeypatch.setattr(flags, "MIN_RESOLVED_FOR_VERDICT", 4)
    resolved_book()
    sc = score.forecast_scores(score.pairs())
    assert "Too early" not in sc["verdict"]
    assert ("Ahead of the market" in sc["verdict"]) == (sc["brier_skill"] > 0)
    doc = score.track_record()
    assert doc["paper_only"] and "financial advice" in doc["disclaimer"] and doc["worst_misses"][0]["brier_ours"] >= doc["worst_misses"][-1]["brier_ours"]
    assert doc["market_beat_us"] == sum(1 for r in doc["resolved"] if r["ours_closer"] is False)


def test_only_the_first_forecast_per_market_counts_and_void_and_uncompared_are_handled():
    store.save_markets([market("a", "resolved", "yes", T0 + timedelta(days=5)), market("b", "void", "void", T0 + timedelta(days=5)),
                        market("c", "resolved", "no", T0 + timedelta(days=5))])
    store.append_snapshots([snap("a", 0.5, T0 - timedelta(hours=1)), snap("b", 0.5, T0 - timedelta(hours=1))])
    store.append_forecast(fc("a", 0.2, T0))
    store.append_forecast(fc("a", 0.99, T0 + timedelta(days=2)))                                  # a better-informed second call must not replace the first
    store.append_forecast(fc("b", 0.5))
    store.append_forecast(fc("c", 0.3))                                                           # resolved, but the market was never priced: scored alone
    ps = score.pairs()
    assert [p.market.id for p in ps] == ["a", "c"] and ps[0].ours == 0.2 and ps[1].market_p is None
    sc = score.forecast_scores(ps)
    assert sc["resolved_with_forecast"] == 2 and sc["compared"] == 1 and sc["brier_ours_all"] is not None


def test_disagreements_list_only_fresh_open_large_gaps():
    store.save_markets([market("a"), market("b"), market("c")])
    store.append_snapshots([snap("a", 0.2, T0), snap("b", 0.5, T0), snap("c", 0.2, T0)])
    store.append_forecast(fc("a", 0.6))
    store.append_forecast(fc("b", 0.55))                                                          # gap too small
    store.append_forecast(fc("c", 0.6, T0 - timedelta(days=30)))                                  # forecast too old to call a current view
    out = score.disagreements(iso(T0 + timedelta(hours=1)))
    assert [d["market_id"] for d in out] == ["a"] and out[0]["gap"] == pytest.approx(0.4)
