"""Markets mirror: Polymarket payload parsing, country/theater mapping, a full pass on fake HTTP, resolution, snapshot spacing."""

from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta

import pytest

from algent_backend.markets import mapping, mirror, polymarket, store

NOW = datetime(2026, 10, 17, 12, 0, tzinfo=UTC)


@pytest.fixture(autouse=True)
def _store(tmp_path, monkeypatch):
    monkeypatch.setenv("ALGENT_MARKETS_STORE", str(tmp_path / "ms"))


def raw_market(mid="m1", question="Will Iran close the Strait of Hormuz by December 31?", *, bid=0.18, ask=0.22, days=60, **extra):
    end = (NOW + timedelta(days=days)).isoformat().replace("+00:00", "Z")
    row = {"id": mid, "question": question, "outcomes": json.dumps(["Yes", "No"]), "outcomePrices": json.dumps([str((bid + ask) / 2), "0.8"]),
           "clobTokenIds": json.dumps([f"tok{mid}", f"nok{mid}"]), "endDate": end, "volumeNum": 90000.0, "liquidityNum": 12000.0,
           "bestBid": bid, "bestAsk": ask, "closed": False, "active": True, "description": "Resolves YES if ...", "slug": f"s-{mid}"}
    row.update(extra)
    return row


def event(markets, tags=("geopolitics",), title="Hormuz", slug="hormuz"):
    return {"id": "e1", "title": title, "slug": slug, "tags": [{"slug": t} for t in tags], "markets": markets}


VOCAB = [mapping.TheaterVocab(id="thr_gulf", name="Iran and the Gulf", countries={"IR", "US"}, terms={"hormuz", "tanker", "shipping"})]


class Fake:
    """Routes the three endpoints; counts calls."""

    def __init__(self, events=None, by_id=None, history=None, fail_tags=()):
        self.events, self.by_id, self.hist, self.fail_tags, self.calls = events or {}, by_id or {}, history or {}, set(fail_tags), []

    def __call__(self, url, params=None):
        self.calls.append(url)
        if url.endswith("/events"):
            if params["tag_slug"] in self.fail_tags:
                raise RuntimeError("boom")
            return self.events.get(params["tag_slug"], [])
        if "/markets/" in url:
            return self.by_id.get(url.rsplit("/", 1)[1])
        if url.endswith("/prices-history"):
            return {"history": self.hist.get(params["market"], [])}
        raise AssertionError(url)


def test_parse_and_price_rules():
    m = polymarket.parse_market(raw_market(), event([]))
    assert m and m.token_yes == "tokm1" and m.tags == ["geopolitics"] and m.url.endswith("/hormuz")
    assert polymarket.yes_price(raw_market(bid=0.18, ask=0.22)) == 0.2
    wide = raw_market(bid=0.0, ask=0.9, lastTradePrice=0.4)
    assert polymarket.yes_price(wide) == 0.4                                   # a gaping book is not a mid
    assert polymarket.parse_market(raw_market(outcomes=json.dumps(["Falcons", "BetBoom"])), event([])) is None
    assert polymarket.parse_market({"id": "x"}, event([])) is None


def test_resolution_reading():
    assert polymarket.resolution(raw_market(closed=True, outcomePrices=json.dumps(["1", "0"])))[0] == "yes"
    assert polymarket.resolution(raw_market(closed=True, outcomePrices=json.dumps(["0", "1"])))[0] == "no"
    assert polymarket.resolution(raw_market(closed=True, outcomePrices=json.dumps(["0.5", "0.5"]), umaResolutionStatus="resolved"))[0] == "void"
    assert polymarket.resolution(raw_market(closed=True, outcomePrices=json.dumps(["0.5", "0.5"])))[0] == ""      # awaiting resolution
    assert polymarket.resolution(raw_market(outcomePrices=json.dumps(["1", "0"])))[0] == ""                       # still trading


def test_history_parses_and_truncates():
    get = Fake(history={"tokm1": [{"t": 1700000000 + i * 86400, "p": 0.1} for i in range(200)]})
    rows = polymarket.history("tokm1", "m1", get)
    assert len(rows) == 90 and rows[0].source == "history" and polymarket.history("", "m1", get) == []


def test_countries_and_mapping():
    assert mapping.countries_in("Will the U.S. invade Iran before 2027?") == {"US", "IR"}
    assert mapping.countries_in("Iranian leadership change") == {"IR"}
    assert mapping.countries_in("Will Mount Vesuvius erupt? Let us see") == set()          # 'us' the pronoun is not the US
    th, cs, score = mapping.map_market("Iran closes Hormuz?", "", VOCAB)
    assert th == ["thr_gulf"] and cs == ["IR"] and score >= 3
    assert mapping.map_market("Who wins the Ballon d'Or?", "", VOCAB)[0] == []


def test_full_pass_keeps_relevant_liquid_markets_and_snapshots():
    ok = raw_market("m1")
    thin = raw_market("m2", "Will Iran sign a deal?", liquidityNum=10.0)
    sport = raw_market("m3", "Will Iran win the match?")
    off = raw_market("m4", "Will a celebrity marry next week?")
    soon = raw_market("m5", "Will Iran do X?", days=0)
    get = Fake(events={"geopolitics": [event([ok, thin, off, soon]), event([sport], tags=("sports",))]},
               history={"tokm1": [{"t": 1700000000, "p": 0.1}, {"t": 1700086400, "p": 0.12}]})
    out = mirror.refresh(get, now=NOW, vocab=VOCAB)
    assert out["discovered"] == 1 and out["new"] == 1 and out["snapshots"] == 1 and out["history"] == 2 and out["tracked_open"] == 1
    m = store.markets()["m1"]
    assert m.theaters == ["thr_gulf"] and m.countries == ["IR"] and m.status == "open"
    live = [s for s in store.snapshots("m1") if s.source == "live"]
    assert [s.p for s in live] == [0.2]
    # a second pass an hour later adds no snapshot (spacing) and no market revision (nothing changed)
    again = mirror.refresh(get, now=NOW + timedelta(hours=1), vocab=VOCAB)
    assert again["snapshots"] == 0 and again["new"] == 0 and len(store.snapshots("m1")) == 3
    later = mirror.refresh(get, now=NOW + timedelta(hours=4), vocab=VOCAB)
    assert later["snapshots"] == 1


def test_resolution_is_recorded_when_market_leaves_the_sweep():
    get = Fake(events={"geopolitics": [event([raw_market("m1")])]})
    mirror.refresh(get, now=NOW, vocab=VOCAB)
    done = raw_market("m1", closed=True, outcomePrices=json.dumps(["0", "1"]), closedTime="2026-10-20 10:00:00+00")
    out = mirror.refresh(Fake(by_id={"m1": done}), now=NOW + timedelta(days=3), vocab=VOCAB)
    m = store.markets()["m1"]
    assert out["resolved"] == 1 and (m.status, m.outcome) == ("resolved", "no") and m.resolved_at.startswith("2026-10-20")
    # resolved is final: a later pass does not look it up or change it
    quiet = Fake()
    mirror.refresh(quiet, now=NOW + timedelta(days=4), vocab=VOCAB)
    assert not any("/markets/" in u for u in quiet.calls)


def test_a_failed_tag_is_recorded_and_the_others_continue():
    get = Fake(events={"world": [event([raw_market("m1")], tags=("world",))]}, fail_tags={"geopolitics"})
    out = mirror.refresh(get, now=NOW, vocab=VOCAB)
    assert out["discovered"] == 1 and "tag:geopolitics" in out["errors"]
    assert store.load_status()["last_ok"]


def test_total_failure_is_an_error_not_an_empty_world():
    from algent_backend.markets import flags

    out = mirror.refresh(Fake(fail_tags=set(flags.TAGS)), now=NOW, vocab=VOCAB)
    assert out["error"] and not store.load_status().get("last_ok")


def test_price_at_uses_the_last_snapshot_before_and_not_a_stale_one():
    from algent_backend.markets.contracts import Snapshot

    rows = [Snapshot(market_id="m", at="2026-10-17T00:00:00+00:00", p=0.3), Snapshot(market_id="m", at="2026-10-17T06:00:00+00:00", p=0.4)]
    assert store.price_at(rows, "2026-10-17T07:00:00+00:00").p == 0.4
    assert store.price_at(rows, "2026-10-17T05:00:00+00:00").p == 0.3
    assert store.price_at(rows, "2026-10-18T07:00:00+00:00") is None
    assert store.price_at(rows, "2026-10-16T07:00:00+00:00") is None
