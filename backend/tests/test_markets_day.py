"""The day book: live browsing filters, order execution under the guards, sell/close, settlement, caps, the run trace, wishes, the schedule and the report."""

from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta

import pytest

from algent_backend.markets import book, browse, day, day_report, flags, forecast, guards, score, store, trader
from algent_backend.markets.contracts import DayRun, Market
from algent_backend.markets.day_prompt import Call, Turn, WishOut
from algent_backend.markets.day_tools import Session
from algent_backend.markets.polymarket import CLOB, GAMMA

NOW = datetime(2026, 10, 24, 12, 0, tzinfo=UTC)


@pytest.fixture(autouse=True)
def _store(tmp_path, monkeypatch):
    for env, name in (("ALGENT_MARKETS_STORE", "ms"), ("ALGENT_CALENDAR_STORE", "cal"), ("ALGENT_STATEMENTS_STORE", "st"), ("ALGENT_SANCTIONS_STORE", "sx"),
                      ("ALGENT_INTEL_STORE", "intel"), ("ALGENT_GEOLEDGER_STORE", "geo"), ("ALGENT_PROFILE_STORE", "prof"), ("ALGENT_RETRIEVAL_STORE", "ret")):
        monkeypatch.setenv(env, str(tmp_path / name))
    monkeypatch.delenv("DATABASE_URL", raising=False)


def raw(mid, hours, *, bid=0.49, ask=0.51, liq=20000.0, vol=50000.0, closed=False, q=None):
    return {"id": mid, "question": q or f"Will thing {mid} happen?", "description": "Resolves YES if it does.", "slug": f"s{mid}", "outcomes": '["Yes", "No"]',
            "clobTokenIds": json.dumps([f"tok{mid}", f"tokno{mid}"]), "endDate": (NOW + timedelta(hours=hours)).strftime("%Y-%m-%dT%H:%M:%SZ"),
            "bestBid": bid, "bestAsk": ask, "liquidityNum": liq, "volumeNum": vol, "closed": closed, "active": not closed}


def event(eid, tags, markets, title=None):
    return {"id": eid, "title": title or f"Event {eid}", "slug": f"ev{eid}", "tags": [{"slug": t} for t in tags], "markets": markets}


WORLD = {"events": [event("e1", ["politics"], [raw("a1", 20, q="Will the ceasefire hold?"), raw("far", 100), raw("thin", 10, liq=100.0)]),
                    event("e2", ["sports", "soccer"], [raw("sp1", 5)]),
                    event("e3", ["economy"], [raw("a2", 30, bid=0.19, ask=0.21, q="Will the Fed cut rates?")])]}


def fake_get(world=None, calls=None):
    world = world or WORLD

    def get(url, params=None):
        if calls is not None:
            calls.append(url)
        if url == f"{GAMMA}/events":
            return world["events"] if not (params or {}).get("offset") else []
        if url == f"{GAMMA}/public-search":
            return {"events": [e for e in world["events"] if (params["q"].split()[0].lower() in json.dumps(e).lower())]}
        if url.startswith(f"{GAMMA}/markets/"):
            mid = url.rsplit("/", 1)[1]
            for e in world["events"]:
                for m in e["markets"]:
                    if m["id"] == mid:
                        return {**m, "events": [{"id": e["id"], "title": e["title"], "slug": e["slug"]}]}
            raise KeyError(mid)
        if url.startswith(f"{GAMMA}/events/"):
            return next(e for e in world["events"] if e["id"] == url.rsplit("/", 1)[1])
        if url == f"{CLOB}/prices-history":
            return {"history": [{"t": int((NOW - timedelta(hours=h)).timestamp()), "p": 0.5 - h / 100} for h in range(12, 0, -1)]}
        if url == f"{CLOB}/book":
            return {"bids": [{"price": "0.49", "size": "1000"}, {"price": "0.2", "size": "500"}], "asks": [{"price": "0.51", "size": "800"}]}
        raise AssertionError(url)

    return get


def sess(**kw):
    return Session(now=NOW, get=fake_get(), corpus=kw.pop("corpus", None), **kw)


# ── browsing ─────────────────────────────────────────────────────────────────────────────────────
def test_search_returns_only_tradable_markets_inside_the_window():
    ids = {v.market.id for v in browse.search("", now=NOW, get=fake_get())}
    assert ids == {"a1", "a2"}                                   # not the 100 h one, not sports, not the thin one
    assert {v.market.id for v in browse.search("ceasefire", now=NOW, get=fake_get())} == {"a1"}
    assert {v.market.id for v in browse.search("", now=NOW, get=fake_get(), ends_within_h=24)} == {"a1"}
    assert {v.market.id for v in browse.search("", now=NOW, get=fake_get(), ends_within_h=9999)} == {"a1", "a2"}   # the horizon is the ceiling
    assert len(browse.search("", now=NOW, get=fake_get(), limit=1)) == 1


def test_search_also_covers_our_mirror_and_tags_the_blocklist():
    m = Market(id="mir", question="Will talks happen?", end_date=(NOW + timedelta(hours=6)).isoformat(), liquidity=9000, volume=9000)
    store.save_markets([m])
    from algent_backend.markets.contracts import Snapshot
    store.append_snapshots([Snapshot(market_id="mir", at=(NOW - timedelta(hours=1)).isoformat(), p=0.4)])
    got = {v.market.id: v.source for v in browse.search("talks", now=NOW, get=fake_get())}
    assert got == {"mir": "mirror"}
    assert "blocklist" in browse.tradable_why(browse.load("sp1", get=fake_get()), NOW)


def test_market_view_has_rules_spread_depth_and_path():
    text = browse.dump(browse.load("a1", get=fake_get(), with_path=True), NOW)
    assert "Resolves YES if it does." in text and "spread 0.02" in text and "book: bid 0.49" in text and "YES path" in text and "20.0 h left" in text


# ── orders ───────────────────────────────────────────────────────────────────────────────────────
def test_buy_fills_at_live_price_plus_slippage_clips_to_the_cap_and_tracks_the_market():
    s = sess()
    ev = s.run(1, Call(tool="buy", market="a1", side="yes", usd=5000, reason="Talks are scheduled.", p_yes=0.7))
    d = store.decisions("day")[0]
    assert d.action == "buy_yes" and d.book == "day" and d.ours == 0.7 and d.rationale == "Talks are scheduled."
    assert d.price == pytest.approx(0.50 + flags.SLIPPAGE) and -d.cash_flow == pytest.approx(flags.DAY_MAX_POSITION_FRAC * flags.DAY_BANKROLL)
    assert d.clips and "position limit" in d.clips[0] and "FILLED" in ev.result and ev.ref == d.id
    m = store.markets()["a1"]
    assert m.origin == "day" and store.snapshots("a1")                   # saved so the mirror marks and resolves it
    assert d.hours_to_end == 20.0


def test_a_refused_order_is_answered_with_its_reason_and_recorded():
    s = sess()
    far = s.run(1, Call(tool="buy", market="far", side="yes", usd=100, reason="x"))
    sp = s.run(1, Call(tool="buy", market="sp1", side="yes", usd=100, reason="x"))
    thin = s.run(1, Call(tool="buy", market="thin", side="no", usd=100, reason="x"))
    assert "NOT FILLED" in far.result and "beyond" in far.result
    assert "blocklist" in sp.result and "too thin" in thin.result
    lines = store.decisions("day")
    assert [d.action for d in lines] == ["hold"] * 3 and all(d.clips and d.clips[0].startswith("refused") for d in lines)
    assert book.cash(lines) == flags.DAY_BANKROLL and "far" not in store.markets()


def test_no_both_sides_cash_floor_and_order_limit(monkeypatch):
    s = sess()
    s.run(1, Call(tool="buy", market="a1", side="yes", usd=100, reason="r"))
    both = s.run(1, Call(tool="buy", market="a1", side="no", usd=100, reason="r"))
    assert "sell it before buying NO" in both.result
    monkeypatch.setattr(flags, "DAY_MAX_ORDERS_PER_RUN", 2)
    over = s.run(2, Call(tool="buy", market="a2", side="yes", usd=100, reason="r"))
    assert "order limit" in over.result and book.cash(s.ds) <= flags.DAY_BANKROLL


def test_exposure_cap_applies_across_markets(monkeypatch):
    monkeypatch.setattr(flags, "DAY_MAX_EXPOSURE_FRAC", 0.06)
    s = sess()
    s.run(1, Call(tool="buy", market="a1", side="yes", usd=500, reason="r"))
    second = s.run(1, Call(tool="buy", market="a2", side="yes", usd=500, reason="r"))
    assert "exposure limit" in second.result and sum(h.cost for h in book.holdings(s.ds).values()) <= 0.06 * flags.DAY_BANKROLL + 0.01


def test_sell_all_partial_and_unknown_position_and_label():
    s = sess()
    s.run(1, Call(tool="buy", market="a1", side="yes", usd=400, reason="r"))
    part = s.run(2, Call(tool="sell", market="P1", usd=100, reason="Took some profit; holding adds little."))
    assert "FILLED sell" in part.result and book.holdings(s.ds)["a1"].cost < 400
    allout = s.run(2, Call(tool="sell", market="a1", all=True, reason="Thesis broke."))
    assert "FILLED sell" in allout.result and not book.holdings(s.ds)
    nothing = s.run(2, Call(tool="sell", market="a1", all=True, reason="again"))
    assert "NOT FILLED" in nothing.result and "no position to sell" in nothing.result
    sells = [d for d in s.ds if d.action == "sell"]
    assert sells[-1].price == pytest.approx(0.50 - flags.SLIPPAGE) and book.cash(s.ds) == pytest.approx(flags.DAY_BANKROLL + book.realised(s.ds), abs=0.05)


def test_sell_is_refused_on_a_closed_market():
    s = sess()
    s.run(1, Call(tool="buy", market="a1", side="yes", usd=200, reason="r"))
    s.get = fake_get({"events": [event("e1", ["politics"], [raw("a1", 20, closed=True)])]})
    assert "closed to trading" in s.run(2, Call(tool="sell", market="a1", all=True, reason="r")).result


def test_day_book_uses_its_own_caps_in_the_shared_guards(monkeypatch):
    f = guards.apply("buy_yes", 5000, held=None, yes_price=0.4, cash=10000, exposure=0, tradable=True, position_frac=0.02, exposure_frac=0.5, bankroll=10000)
    assert -f.cash_flow == pytest.approx(200)
    f = guards.apply("buy_yes", 5000, held=None, yes_price=0.4, cash=10000, exposure=0, tradable=True)      # the daily defaults are unchanged
    assert -f.cash_flow == pytest.approx(flags.MAX_POSITION_FRAC * flags.BANKROLL)


# ── settlement, equity, forecasting ──────────────────────────────────────────────────────────────
def test_settlement_pays_the_day_book_and_marks_its_own_curve():
    s = sess()
    s.run(1, Call(tool="buy", market="a1", side="yes", usd=300, reason="r"))
    assert [p.book for p in book.mark(NOW) if p.book == "day"] == ["day"]
    store.save_markets([store.markets()["a1"].model_copy(update={"status": "resolved", "outcome": "yes", "resolved_at": NOW.isoformat()})])
    assert trader.settle(NOW + timedelta(hours=21), "day") == 1
    ds = store.decisions("day")
    assert ds[-1].action == "settle" and ds[-1].realised > 0 and not book.holdings(ds)
    assert book.cash(ds) > flags.DAY_BANKROLL
    assert store.decisions("daily") == [] and trader.settle(NOW, "day") == 0


def test_a_market_only_the_day_book_brought_in_is_never_forecast():
    s = sess()
    s.run(1, Call(tool="buy", market="a1", side="yes", usd=300, reason="r"))
    from algent_backend.markets.contracts import Snapshot
    store.append_snapshots([Snapshot(market_id="a1", at=NOW.isoformat(), p=0.5)])
    assert forecast.candidates(NOW) == []


# ── the tools ────────────────────────────────────────────────────────────────────────────────────
def test_portfolio_performance_size_and_watchlist():
    s = sess()
    assert "no open positions" in s.run(1, Call(tool="portfolio")).result
    s.run(1, Call(tool="buy", market="a1", side="yes", usd=400, reason="r"))
    pf = s.run(1, Call(tool="portfolio")).result
    assert "P1 [a1] YES" in pf and "at risk" in pf and "h to resolution" in pf and "unrealised" in pf and "realised on earlier sells" in pf
    s.run(2, Call(tool="sell", market="a1", all=True, reason="r"))
    perf = s.run(2, Call(tool="performance")).result
    assert "closed trades 1" in perf and "best:" in perf and "by horizon:" in perf and "by category:" in perf
    sz = s.run(2, Call(tool="size", market="a2", p_yes=0.5)).result
    assert "YES:" in sz and "after the caps" in sz and "NO: all-in price" in sz and "no edge" in sz           # priced 0.20: YES has the edge, NO has none
    assert "give p_yes" in s.run(2, Call(tool="size", market="a2")).result
    w = s.run(3, Call(tool="watchlist", action="add", market="a2", reason="Waiting for the vote.")).result
    assert "a2" in w and "Waiting for the vote." in w
    assert "a2" in store.watchlist() and "a2" in Session(now=NOW, get=fake_get()).watch_text()                     # persisted between runs
    assert "empty" in s.run(3, Call(tool="watchlist", action="remove", market="a2")).result


def test_corpus_tools_are_logged_and_citations_must_have_been_shown():
    class Corpus:
        def search(self, arg, **kw):
            return [{"id": "daily:1", "kind": "daily", "date": "2026-10-23", "title": "Talks set"}, {"id": "market:x", "product": "markets", "title": "price"}]

    s = sess(corpus=Corpus())
    out = s.run(1, Call(tool="search", query="talks")).result
    assert "daily:1" in out and "market:x" not in out                    # the blindness filter is the research layer's
    s.run(1, Call(tool="buy", market="a1", side="yes", usd=100, reason="r", cited=["daily:1", "invented:9"]))
    assert store.decisions("day")[0].evidence_ids == ["daily:1"]
    assert s.queries == ["search(talks)"]
    assert "not available" in sess().run(1, Call(tool="entity", query="Iran")).result


def test_request_research_files_a_gap_for_the_day_book():
    s = sess()
    assert "filed" in s.run(1, Call(tool="request_research", query="Port of Odessa throughput", reason="size a shipping market")).result
    g = store.gaps()[0]
    assert g.book == "day" and g.topic == "Port of Odessa throughput"


# ── the loop ─────────────────────────────────────────────────────────────────────────────────────
class Script:
    """A stub model: replays turns; each call costs ``usd``."""

    def __init__(self, turns, usd=0.03):
        self.turns, self.usd, self.tasks = list(turns), usd, []

    def __call__(self, task, role=""):
        self.tasks.append(task)
        return (self.turns.pop(0) if self.turns else Turn(done=True, summary="out of script")), self.usd


def full_run():
    return Script([Turn(notes="look", calls=[Call(tool="search_markets", query="ceasefire"), Call(tool="market", market="a1")]),
                   Turn(notes="act", calls=[Call(tool="buy", market="a1", side="yes", usd=200, reason="Talks are on.", p_yes=0.7), Call(tool="request_research", query="mediator statements", reason="x")]),
                   Turn(done=True, summary="Bought the ceasefire market; watching the vote.",
                        wishes=[WishOut(topic="Live parliament vote tallies", why="a1 turns on the vote", market="a1", source="parliament feed"),
                                WishOut(topic="live parliament vote tallies", why="dup", market="a1")])])


def test_a_run_writes_the_full_trace_orders_wishes_and_cost():
    a = full_run()
    rep = day.run(ask=a, now=NOW, get=fake_get(), corpus=None)
    assert rep["turns"] == 3 and rep["orders"] == 1 and rep["filled"] == 1 and rep["stopped"] == "done" and rep["usd"] == pytest.approx(0.09)
    r = store.day_runs()[0]
    assert [e.tool for e in r.events] == ["portfolio", "search_markets", "market", "buy", "request_research"] and r.events[0].turn == 0
    assert r.events[1].args == {"query": "ceasefire"} and "a1 |" in r.events[1].result and r.orders == [store.decisions("day")[0].id]
    assert r.considered[0]["id"] == "a1" and r.summary.startswith("Bought") and r.usd == pytest.approx(0.09) and r.tokens > 0 and r.equity is not None
    assert "search_markets(ceasefire)"[:14] not in r.queries and "request_research(mediator statements)" in r.queries
    ws = store.wishes()
    assert len(ws) == 1 and ws[0].source == "parliament feed" and ws[0].run_id == r.id and ws[0].question == "Will the ceasefire hold?"
    assert "TURN 2 of" in a.tasks[1] and "a1 | Will the ceasefire hold?" in a.tasks[1] and "WATCHLIST" in a.tasks[0]


def test_tool_call_turn_and_run_budget_caps(monkeypatch):
    monkeypatch.setattr(flags, "DAY_MAX_TOOL_CALLS", 3)
    many = Script([Turn(calls=[Call(tool="search_markets")] * 5), Turn(done=True)])
    rep = day.run(ask=many, now=NOW, get=fake_get(), corpus=None)
    assert rep["tool_calls"] == 3 and rep["stopped"] == "tool-call limit"
    monkeypatch.setattr(flags, "DAY_MAX_TOOL_CALLS", 24)
    monkeypatch.setattr(flags, "DAY_MAX_TURNS", 2)
    endless = Script([Turn(calls=[Call(tool="portfolio")])] * 5)
    assert day.run(ask=endless, now=NOW + timedelta(minutes=1), get=fake_get(), corpus=None)["stopped"] == "turn limit"
    assert len(endless.tasks) == 2 and "NEAR THE END" in endless.tasks[1]
    monkeypatch.setattr(flags, "DAY_MAX_TURNS", 7)
    pricey = Script([Turn(calls=[Call(tool="portfolio")])] * 6, usd=0.09)
    rep = day.run(ask=pricey, now=NOW + timedelta(minutes=2), get=fake_get(), corpus=None)
    assert rep["stopped"] == "run budget reached" and rep["turns"] == 1 and rep["usd"] == pytest.approx(0.09)


def test_day_budget_stops_a_run_before_any_call_and_a_failed_call_keeps_the_orders():
    store.append_day_run(DayRun(id="dr-x", at=NOW.isoformat(), day=NOW.date().isoformat(), usd=flags.DAY_MAX_USD_PER_DAY))
    assert "day budget" in day.run(ask=Script([]), now=NOW, get=fake_get(), corpus=None)["stopped"]
    nxt = NOW + timedelta(days=1)

    class Boom(Script):
        def __call__(self, task, role=""):
            if len(self.tasks) == 1:
                raise RuntimeError("provider down")
            return super().__call__(task, role)

    rep = day.run(ask=Boom([Turn(calls=[Call(tool="buy", market="a1", side="yes", usd=100, reason="r")])]), now=nxt, get=fake_get(), corpus=None)
    assert rep["stopped"].startswith("model call failed") and len(store.decisions("day")) == 1


def test_a_run_with_no_orders_is_a_valid_cash_run_and_the_switch_works(monkeypatch):
    rep = day.run(ask=Script([Turn(done=True, summary="Nothing worth it; holding cash.")]), now=NOW, get=fake_get(), corpus=None)
    assert rep["orders"] == 0 and rep["stopped"] == "done" and store.day_runs()[0].summary.startswith("Nothing")
    monkeypatch.setattr(flags, "DAY_ENABLED", False)
    assert "switched off" in day.run(ask=Script([]), now=NOW, get=fake_get(), corpus=None)["stopped"]


def test_the_expected_cost_a_day_fits_the_caps():
    assert flags.DAY_MAX_USD_PER_DAY <= 0.50 and flags.DAY_MAX_USD_PER_RUN <= 0.15 and round(len(flags.DAY_RUN_HOURS) * flags.DAY_MAX_USD_PER_RUN, 6) >= flags.DAY_MAX_USD_PER_DAY
    assert flags.DAY_MAX_TURNS * flags.DAY_CALL_CAP_USD >= flags.DAY_MAX_USD_PER_RUN


# ── the schedule ─────────────────────────────────────────────────────────────────────────────────
def test_the_registry_job_runs_three_times_a_day_off_the_crunch_and_validates():
    from algent_backend.ops.jobq.capacity import daily_starts
    from algent_backend.ops.products import validate, views

    job = views.job("markets-day")[1]
    assert job.argv == ("markets", "day") and job.spend == "capped" and job.prio == 1
    starts = daily_starts(job.when())
    assert starts == [h * 60 + flags.DAY_RUN_MINUTE for h in flags.DAY_RUN_HOURS] and len(starts) == 3
    assert not any(5 * 60 <= m < 7 * 60 for m in starts)
    assert validate.validate() == []


# ── the report ───────────────────────────────────────────────────────────────────────────────────
def test_the_report_withholds_win_rates_until_the_verdict_threshold_and_shows_runs_and_wishes(monkeypatch):
    day.run(ask=full_run(), now=NOW, get=fake_get(), corpus=None)
    s = Session(now=NOW + timedelta(hours=1), get=fake_get())
    s.run(1, Call(tool="sell", market="a1", all=True, reason="Price reached what I think it is worth."))
    book.mark(NOW)
    sec = day_report.section(NOW.date().isoformat())
    assert sec["summary"]["closed"] == 1 and sec["limits"]["max_usd_per_day"] == flags.DAY_MAX_USD_PER_DAY and sec["enabled"] and sec["run_hours"] == [8, 14, 20]
    h = {g["label"]: g for g in sec["by_horizon"]}["6 to 24 hours"]
    assert h["n"] == 1 and h["shown"] is False and h["hit_rate"] is None and h["pnl"] is None
    monkeypatch.setattr(flags, "MIN_RESOLVED_FOR_VERDICT", 1)
    h = {g["label"]: g for g in day_report.section(NOW.date().isoformat())["by_horizon"]}["6 to 24 hours"]
    assert h["shown"] and h["hit_rate"] is not None and h["pnl"] is not None
    run = sec["runs"][0]
    assert run["orders"][0]["reason"] == "Talks are on." and run["n_considered"] >= 1 and run["queries"] and run["usd"] > 0
    assert sec["wishes"][0]["topic"] == "Live parliament vote tallies" and sec["wishes"][0]["source"] == "parliament feed" and sec["wishes"][0]["runs"] == 1
    assert [r["hours_left"] for r in sec["open_positions"]] == [] and sec["log"][0]["action"] == "sell" and sec["last_at"].startswith(NOW.date().isoformat())
    held = Session(now=NOW + timedelta(hours=2), get=fake_get())
    held.run(1, Call(tool="buy", market="a2", side="no", usd=100, reason="r"))
    pos = day_report.section(NOW.date().isoformat())["open_positions"][0]
    assert pos["now_at"].startswith(NOW.date().isoformat()) and pos["ends_at"].endswith(":00") and pos["url"].startswith("https://polymarket.com/event/")


def test_wishes_aggregate_across_runs_by_distinct_runs():
    for i in range(3):
        day.run(ask=Script([Turn(done=True, wishes=[WishOut(topic="Live parliament vote tallies", source="feed")])]), now=NOW + timedelta(hours=i), get=fake_get(), corpus=None)
    day.run(ask=Script([Turn(done=True, wishes=[WishOut(topic="Satellite port imagery")])]), now=NOW + timedelta(hours=5), get=fake_get(), corpus=None)
    top = day_report.wishes_top()
    assert top[0]["topic"] == "Live parliament vote tallies" and top[0]["runs"] == 3 and top[1]["runs"] == 1


def test_the_published_document_carries_the_day_book_additively():
    doc = score.track_record()
    assert doc["schema"] == "ohmega.track-record/2" and doc["day"]["summary"]["open"] == 0 and doc["day"]["runs"] == [] and doc["day"]["wishes"] == []
    assert doc["day"]["horizon_hours"] == flags.DAY_HORIZON_H and "trader" in doc and "fast" in doc


def test_cli_day_dry_run_and_refresh_settles_the_day_book(capsys):
    import argparse

    from algent_backend.cli.newsroom import markets as cli

    cli.run_day(argparse.Namespace(dry_run=True))
    out = json.loads(capsys.readouterr().out)
    assert out["run_hours"] == [8, 14, 20] and out["caps"]["day"] == flags.DAY_MAX_USD_PER_DAY
