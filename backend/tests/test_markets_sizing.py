"""Trust-weighted sizing (markets/sizing.py) and skill vs the market (bot_forecasts.skill_stats): shrink, trust bounds, the extreme-price cap, the no-edge hold,
the hourly-bot repro (p=0.995 at 97c), one-forecast-per-market dedupe, the contested split and "too early"."""

from __future__ import annotations

import pytest
from test_markets_day import _store  # noqa: F401  (autouse store fixture, re-exported so it applies here)

from algent_backend.markets import bot_forecasts, flags, guards, paper, sizing, store
from algent_backend.markets.contracts import BotForecast, Market


def block(n=30, mean=0.02, se=0.01):
    return {"n": n, "shown": True, "mean": mean, "se": se}


def test_the_probability_is_shrunk_toward_the_price_by_trust():
    assert sizing.shrink(0.9, 0.5, 1.0) == pytest.approx(0.9) and sizing.shrink(0.9, 0.5, 0.0) == pytest.approx(0.5)
    assert sizing.shrink(0.9, 0.5, 0.3) == pytest.approx(0.62)
    c = sizing.ceiling(0.9, "yes", 0.51, 10000.0, 0.3)               # price 0.50 + 0.01 slippage
    assert c.q == pytest.approx(0.3 * 0.9 + 0.7 * 0.50) and c.stake == pytest.approx(flags.KELLY_FRACTION * (c.q - 0.51) / 0.49 * 10000, abs=0.01)
    no = sizing.ceiling(0.9, "no", 0.51, 10000.0, 0.3)                # betting NO on a 90% YES: shrunk p(NO) 0.38 is below the 0.51 cost
    assert no.stake == 0.0 and no.why == "no edge after trust shrink"


def test_trust_starts_at_the_prior_moves_with_skill_and_stays_inside_its_bounds():
    prior = flags.TRUST_PRIOR
    assert sizing.trust_from(None) == prior and sizing.trust_from({"contested": {"n": 4, "shown": False, "mean": None, "se": None}}) == prior
    assert sizing.trust_from({"contested": block(mean=0.0, se=0.01)}) == prior
    ts = [sizing.trust_from({"contested": block(mean=m, se=0.01)}) for m in (-0.1, -0.02, -0.005, 0.0, 0.005, 0.02, 0.1)]
    assert ts == sorted(ts) and len(set(ts)) > 3                       # monotone in skill, not flat
    assert ts[0] == flags.TRUST_MIN and ts[-1] == flags.TRUST_MAX      # clamped both ways
    assert sizing.trust_from({"contested": block(mean=0.01, se=0.01)}) < sizing.trust_from({"contested": block(mean=0.01, se=0.002)})   # same skill, tighter error: more trust
    assert sizing.trust_from({"contested": block(mean=-0.01)}) < prior


def test_a_cost_above_the_extreme_price_caps_the_stake_at_the_max_loss_share():
    c = sizing.ceiling(0.999, "yes", 0.95, 10000.0, 1.0)              # huge Kelly, but the whole stake is the loss
    assert c.stake == pytest.approx(flags.MAX_LOSS_FRAC_EXTREME * 10000) and "extreme" in c.why
    mid = sizing.ceiling(0.999, "yes", 0.60, 10000.0, 1.0)
    assert mid.stake > c.stake and mid.why == "trust-weighted Kelly"   # not extreme: Kelly alone binds (the position cap is guards')


def test_no_edge_after_the_shrink_is_held_with_its_reason():
    f = guards.apply("buy_yes", 400, held=None, yes_price=0.60, cash=1e4, exposure=0, tradable=True, p_yes=0.62, trust=0.3)   # 0.6 + 0.3*0.02 = 0.606 < 0.61
    assert f.action == "hold" and "no edge after trust shrink" in f.clips[0]


def test_the_stake_is_honoured_only_up_to_the_ceiling_and_says_so():
    f = guards.apply("buy_yes", 5000, held=None, yes_price=0.50, cash=1e4, exposure=0, tradable=True, p_yes=0.8, trust=0.3)
    want = sizing.ceiling(0.8, "yes", 0.51, 10000.0, 0.3).stake
    assert -f.cash_flow == pytest.approx(want) and want < 500 and f.clips[0].startswith(f"trimmed to trust-weighted Kelly ${want:.0f}")
    small = guards.apply("buy_yes", 20, held=None, yes_price=0.50, cash=1e4, exposure=0, tradable=True, p_yes=0.8, trust=0.3)
    assert -small.cash_flow == 20 and not small.clips                  # under the ceiling: untouched


def test_the_hourly_case_a_near_certain_side_at_97c_is_never_a_500_dollar_bet():
    kw = dict(held=None, yes_price=0.97, cash=1e4, exposure=0, tradable=True, p_yes=0.995)
    prior = guards.apply("buy_yes", 500, **kw)                         # trust at the prior: 0.3*0.995 + 0.7*0.97 = 0.9775 < 0.98 all-in
    assert prior.action == "hold" and "no edge after trust shrink" in prior.clips[0]
    earned = guards.apply("buy_yes", 500, trust=flags.TRUST_MAX, **kw)  # even maximal trust: capped at 1% of the bankroll
    assert earned.action == "buy_yes" and -earned.cash_flow <= flags.MAX_LOSS_FRAC_EXTREME * 10000 + 1e-6


def test_floor_stake_and_the_rule_book_share_the_same_maths():
    assert guards.floor_stake(0.5, "yes", 0.5, 10000, 1.0) == flags.TRADE_MIN_TICKET                       # no edge: the ticket
    assert guards.floor_stake(0.7, "yes", 0.5, 10000, 1.0) == pytest.approx(sizing.ceiling(0.7, "yes", 0.51, 10000, 1.0).stake, abs=0.01)
    assert guards.floor_stake(0.7, "yes", 0.5, 10000, 0.3) < guards.floor_stake(0.7, "yes", 0.5, 10000, 1.0)
    assert paper.kelly_stake(0.56, 0.5) == pytest.approx(0.03 * flags.BANKROLL)                             # the retired rule book: full trust, unchanged


# ── skill vs market ─────────────────────────────────────────────────────────────────────────────
def fcst(i, mid, p, market, at):
    return BotForecast(id=f"f{i}", strategy="s", run_id=f"r{i}", market_id=mid, at=at, day=at[:10], p=p, market=market)


def seed(rows, markets, monkeypatch, need=2):
    monkeypatch.setattr(flags, "FORECAST_MIN_RESOLVED", need)
    store.append_bot_forecasts(rows)
    store.save_markets(markets)


def test_skill_counts_one_forecast_per_market_the_last_before_resolution(monkeypatch):
    rows = [fcst(i, "m1", 0.9 if i == 19 else 0.1, 0.5, f"2026-10-{10 + i}T10:00:00+00:00") for i in range(20)]          # 20 restatements, the last is the good one
    rows += [fcst(100, "m2", 0.4, 0.5, "2026-10-21T10:00:00+00:00"), fcst(101, "m2", 0.9, 0.5, "2026-10-30T10:00:00+00:00")]   # m2: the second is AFTER it resolved
    seed(rows, [Market(id="m1", question="q", status="resolved", outcome="yes", resolved_at="2026-11-29T00:00:00+00:00"),
                Market(id="m2", question="q", status="resolved", outcome="no", resolved_at="2026-10-25T00:00:00+00:00")], monkeypatch)
    k = bot_forecasts.skill_stats("s")
    assert k["all"]["n"] == 2 and k["all"]["shown"]                                                          # 22 forecasts, 2 markets
    gain_m1, gain_m2 = 0.25 - 0.01, 0.25 - 0.16                                                              # market 0.5 vs bot 0.9 (yes) / 0.4 (no)
    assert k["all"]["mean"] == pytest.approx((gain_m1 + gain_m2) / 2, abs=1e-4) and k["all"]["se"] == pytest.approx(abs(gain_m1 - gain_m2) / 2, abs=1e-4)


def test_contested_is_split_by_the_market_price_at_forecast_time(monkeypatch):
    rows = [fcst(1, "a", 0.9, 0.5, "2026-10-20T10:00:00+00:00"), fcst(2, "b", 0.9, 0.6, "2026-10-20T10:00:00+00:00"),
            fcst(3, "c", 0.999, 0.97, "2026-10-20T10:00:00+00:00"), fcst(4, "d", 0.02, 0.03, "2026-10-20T10:00:00+00:00")]     # c, d: near-decided, outside the band
    seed(rows, [Market(id=i, question="q", status="resolved", outcome="yes" if i != "d" else "no") for i in "abcd"], monkeypatch)
    k = bot_forecasts.skill_stats("s")
    assert k["all"]["n"] == 4 and k["contested"]["n"] == 2
    assert k["contested"]["mean"] == pytest.approx(((0.25 - 0.01) + (0.16 - 0.01)) / 2, abs=1e-4)
    assert k["contested"]["mean"] > k["all"]["mean"]                                                         # the easy near-certain markets add little over the market
    assert bot_forecasts.summary("s")["skill"] == k                                                          # published with the strategy's forecasts block


def test_skill_is_withheld_until_enough_have_resolved(monkeypatch):
    seed([fcst(1, "a", 0.9, 0.5, "2026-10-20T10:00:00+00:00"), fcst(2, "b", 0.9, 0.5, "2026-10-20T10:00:00+00:00")],
         [Market(id="a", question="q", status="resolved", outcome="yes"), Market(id="b", question="q")], monkeypatch, need=3)
    k = bot_forecasts.skill_stats("s")
    assert k["all"] == {"n": 1, "shown": False, "mean": None, "se": None} and k["contested"]["shown"] is False
    assert sizing.trust("s") == flags.TRUST_PRIOR                                                            # no skill shown, no trust earned


def test_a_forecast_made_after_the_market_ended_is_not_scored():
    from types import SimpleNamespace as NS

    from algent_backend.markets.bot_forecasts import scorable
    m = NS(status="resolved", outcome="no", end_date="2026-10-30T20:00:00Z", resolved_at="2026-10-30T20:35:00+00:00")
    assert scorable(NS(at="2026-10-30T19:25:00+00:00"), m)
    assert not scorable(NS(at="2026-10-30T20:31:00+00:00"), m)            # after the end, before settlement: the price already shows the answer
