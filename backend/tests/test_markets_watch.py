"""The mirror's watch-set: markets our bots forecast, traded, rested on or the lab asked about are fetched by id and kept until they resolve."""

from __future__ import annotations

import json
from datetime import timedelta

import pytest

from algent_backend.markets import flags, mirror, store, watch
from algent_backend.markets.contracts import BotForecast, Decision, Forecast, RestingOrder
from tests.test_markets_mirror import NOW, VOCAB, Fake, raw_market


@pytest.fixture(autouse=True)
def _stores(tmp_path, monkeypatch):
    monkeypatch.setenv("ALGENT_MARKETS_STORE", str(tmp_path / "ms"))
    monkeypatch.setenv("ALGENT_EXPERIMENT_STORE", str(tmp_path / "ex"))


def _bf(mid):
    return BotForecast(id=f"bf-{mid}", strategy="hourly", run_id="r", market_id=mid, at=NOW.isoformat(), day="2026-10-17", p=0.4, market=0.3)


def _seed_everything():
    store.append_bot_forecasts([_bf("f1")])
    store.append_forecast(Forecast(id="fc", market_id="f2", made_at=NOW.isoformat(), p=0.5))
    store.append_decisions([Decision(id="d1", market_id="t1", at=NOW.isoformat(), day="2026-10-17", action="hold", book="fast")])
    store.append_resting([RestingOrder(id="o1", book="day", market_id="r1", action="buy_yes", limit_price=0.3, p_yes=0.4, placed_at=NOW.isoformat(),
                                       expires_at=(NOW + timedelta(days=1)).isoformat())])
    qdir = watch.Path(watch.os.environ["ALGENT_EXPERIMENT_STORE"]) / "questions"
    qdir.mkdir(parents=True)
    (qdir / "q1.json").write_text(json.dumps({"id": "q1", "source": "market:l1"}), encoding="utf-8")
    (qdir / "q2.json").write_text(json.dumps({"id": "q2", "source": "manual"}), encoding="utf-8")


def test_watch_set_names_forecast_traded_rested_and_lab_markets():
    _seed_everything()
    w = watch.watched()
    assert w == {"f1": {"forecast"}, "f2": {"forecast"}, "t1": {"traded"}, "r1": {"rested"}, "l1": {"lab"}}


def test_missing_watched_markets_are_backfilled_and_their_outcome_recorded():
    _seed_everything()
    done = raw_market("f1", closed=True, outcomePrices=json.dumps(["1", "0"]), closedTime="2026-10-16 10:00:00+00")
    still = raw_market("l1", "Will Iran sign a deal by Friday?", days=3)
    get = Fake(by_id={"f1": done, "l1": still})                    # f2, t1, r1 are not found upstream: skipped, not fatal
    out = mirror.refresh(get, now=NOW, vocab=VOCAB)
    ms = store.markets()
    assert out["watch_missing"] == 5 and out["watch_fetched"] == 2 and out["resolved"] == 1
    assert (ms["f1"].status, ms["f1"].outcome) == ("resolved", "yes") and ms["f1"].origin == "watch"
    assert ms["l1"].status == "open" and ms["l1"].origin == "watch" and [s.p for s in store.snapshots("l1") if s.source == "live"] == [0.2]
    again = Fake(by_id={"l1": still})                               # the resolved one is final; the open one is tracked like any other
    mirror.refresh(again, now=NOW + timedelta(hours=4), vocab=VOCAB)
    assert not any(u.endswith("/markets/f1") for u in again.calls)


def test_a_watched_market_is_not_forecast_by_the_desk():
    from algent_backend.markets import forecast

    store.append_bot_forecasts([_bf("l1")])
    mirror.refresh(Fake(by_id={"l1": raw_market("l1", days=3)}), now=NOW, vocab=VOCAB)
    assert store.markets()["l1"].origin == "watch"
    assert "l1" not in [m.id for m in forecast.candidates(NOW)]


def test_watch_is_bounded_per_pass_and_can_be_switched_off(monkeypatch):
    store.append_bot_forecasts([_bf(f"w{i}") for i in range(5)])
    monkeypatch.setattr(flags, "WATCH_MAX_FETCH", 2)
    get = Fake(by_id={f"w{i}": raw_market(f"w{i}", days=3) for i in range(5)})
    assert mirror.refresh(get, now=NOW, vocab=VOCAB)["watch_fetched"] == 2
    monkeypatch.setattr(flags, "WATCH_ENABLED", False)
    off = mirror.refresh(Fake(), now=NOW + timedelta(hours=1), vocab=VOCAB)
    assert "watch_fetched" not in off
