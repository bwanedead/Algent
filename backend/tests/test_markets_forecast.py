"""Blind forecasts: evidence assembly without prices, selection, day caps, immutability, honest handling of bad model output."""

from __future__ import annotations

import inspect
from datetime import UTC, date, datetime, timedelta
from types import SimpleNamespace

import pytest

from algent_backend.markets import evidence, flags, forecast, store
from algent_backend.markets.contracts import Market, Snapshot

NOW = datetime(2026, 10, 17, 12, 0, tzinfo=UTC)
RECORD = {"date": "2026-10-17", "theaters": [{
    "theater_id": "thr_gulf", "name": "Iran and the Gulf", "bottom_line": "Talks are stalled; Hormuz traffic is normal.",
    "outlook": "No deal expected this month.", "watch_next": ["Oman mediation round"], "since_yesterday": "Nothing decisive.",
    "developments": [{"headline": "Tehran rejects text", "verification": "researched"}],
    "pulses": [{"name": "Military confrontation", "position": 41.0, "band": "severe", "change_7d": 2.0}]}]}


@pytest.fixture(autouse=True)
def _store(tmp_path, monkeypatch):
    monkeypatch.setenv("ALGENT_MARKETS_STORE", str(tmp_path / "ms"))
    monkeypatch.setenv("ALGENT_CALENDAR_STORE", str(tmp_path / "cal"))
    monkeypatch.setenv("ALGENT_STATEMENTS_STORE", str(tmp_path / "st"))
    monkeypatch.setenv("ALGENT_SANCTIONS_STORE", str(tmp_path / "sx"))


def seed(mid="m1", price=0.3, theaters=("thr_gulf",), end_days=60, volume=1e5):
    store.save_markets([Market(id=mid, question=f"Will thing {mid} happen by year end?", description="Resolves YES if it does.",
                               end_date=(NOW + timedelta(days=end_days)).isoformat(), volume=volume, theaters=list(theaters), countries=["IR"])])
    store.append_snapshots([Snapshot(market_id=mid, at=(NOW - timedelta(hours=2)).isoformat(), p=price)])


class FakeAsk:
    def __init__(self, p=0.12, usd=0.01, cited=("theater:thr_gulf", "theater:invented")):
        self.tasks, self.p, self.usd, self.cited = [], p, usd, cited

    def __call__(self, task, role=""):
        self.tasks.append(task)
        return SimpleNamespace(probability=self.p, rationale="Base rate low. Talks stalled.", cited=list(self.cited)), self.usd


def test_evidence_uses_the_mapped_sections_and_cites_ids():
    m = Market(id="m", question="q", theaters=["thr_gulf", "thr_other"], countries=["IR"])
    ev = evidence.build(m, today=date(2026, 10, 17), record=RECORD)
    assert "[theater:thr_gulf]" in ev.text and "Talks are stalled" in ev.text and "Pulse Military confrontation: 41.0/100" in ev.text
    assert ev.ids == ["theater:thr_gulf"]                    # a mapped theater absent from the daily contributes nothing


def test_the_evidence_module_cannot_see_prices():
    assert not hasattr(evidence, "store") and not hasattr(evidence, "Snapshot")
    assert "price" not in inspect.signature(evidence.build).parameters
    assert "price_at" not in inspect.getsource(evidence) and "snapshots" not in inspect.getsource(evidence).split('"""', 2)[2]


def test_the_prompt_the_model_sees_contains_no_market_number():
    seed(price=0.3731)
    ask = FakeAsk()
    forecast.run(ask=ask, now=NOW, record=RECORD)
    task = ask.tasks[0]
    assert "0.3731" not in task and "37" not in task and "Will thing m1" in task and "Talks are stalled" in task
    assert "NOT told what any prediction market" in forecast.ROLE


def test_a_forecast_is_stored_clamped_with_only_real_citations_and_cost():
    seed()
    out = forecast.run(ask=FakeAsk(p=0.0, usd=0.02), now=NOW, record=RECORD)
    assert out["made"] == 1 and out["usd"] == 0.02
    f = store.forecasts()[0]
    assert f.p == flags.P_MIN and f.evidence_ids == ["theater:thr_gulf"] and f.usd == 0.02 and f.made_at.startswith("2026-10-17")
    assert f.prompt_version == forecast.PROMPT_VERSION and f.theaters == ["thr_gulf"]


def test_selection_skips_extremes_recent_forecasts_closed_and_unpriced():
    seed("a", price=0.5)
    seed("b", price=0.01)                                    # priced at the extreme: nothing to disagree about
    seed("c", price=0.99)
    seed("d", price=0.4, end_days=-1)                        # already past its end
    store.save_markets([Market(id="e", question="no price yet")])
    assert [m.id for m in forecast.candidates(NOW)] == ["a"]
    forecast.run(ask=FakeAsk(), now=NOW, record=RECORD)
    assert forecast.candidates(NOW + timedelta(days=1)) == []                       # forecast within REFORECAST_DAYS
    # a week on the mirror has not run since (its newest price is stale): nothing is forecast against a dead mirror
    assert forecast.candidates(NOW + timedelta(days=flags.REFORECAST_DAYS + 1)) == []


def test_markets_with_evidence_go_first_then_volume():
    seed("plain", theaters=(), volume=9e6)
    seed("mapped", theaters=("thr_gulf",), volume=1e4)
    assert [m.id for m in forecast.candidates(NOW)] == ["mapped", "plain"]


def test_day_count_and_dollar_caps(monkeypatch):
    for i in range(7):
        seed(f"m{i}")
    monkeypatch.setattr(flags, "MAX_FORECASTS_PER_DAY", 3)
    assert forecast.run(ask=FakeAsk(), now=NOW, record=RECORD)["made"] == 3
    again = forecast.run(ask=FakeAsk(), now=NOW, record=RECORD)
    assert again["made"] == 0 and "day limit" in again["stopped"]
    monkeypatch.setattr(flags, "MAX_FORECASTS_PER_DAY", 40)
    monkeypatch.setattr(flags, "MAX_FORECAST_USD_PER_DAY", 0.035)
    out = forecast.run(ask=FakeAsk(usd=0.02), now=NOW + timedelta(days=1), record=RECORD)
    assert out["made"] == 2 and "budget" in out["stopped"]                          # stops once the day's dollars are spent


def test_bad_model_output_and_failures_are_skipped_not_stored():
    seed("a")
    seed("b")

    def flaky(task, role=""):
        if "thing a" in task:
            raise RuntimeError("provider down")
        return SimpleNamespace(probability=1.7, rationale="x", cited=[]), 0.01

    out = forecast.run(ask=flaky, now=NOW, record=RECORD)
    assert out["made"] == 0 and out["failed"] == 2 and store.forecasts() == []


def test_a_budget_refusal_ends_the_pass():
    seed("a")
    seed("b")
    calls = []

    class BudgetRefusedError(RuntimeError):
        pass

    def refuse(task, role=""):
        calls.append(1)
        raise BudgetRefusedError("halt")

    out = forecast.run(ask=refuse, now=NOW, record=RECORD)
    assert len(calls) == 1 and "budget gate" in out["stopped"]


def test_forecasts_are_append_only_and_switchable(monkeypatch):
    seed()
    forecast.run(ask=FakeAsk(p=0.2), now=NOW, record=RECORD)
    first = store.forecasts()[0]
    store.append_snapshots([Snapshot(market_id="m1", at=(NOW + timedelta(days=8)).isoformat(), p=0.3)])
    forecast.run(ask=FakeAsk(p=0.9), now=NOW + timedelta(days=8), record=RECORD)
    rows = store.forecasts()
    assert len(rows) == 2 and rows[0] == first and rows[1].p == 0.9                    # the old line is untouched
    monkeypatch.setattr(flags, "FORECAST_ENABLED", False)
    assert "switched off" in forecast.run(ask=FakeAsk(), now=NOW + timedelta(days=30), record=RECORD)["stopped"]
