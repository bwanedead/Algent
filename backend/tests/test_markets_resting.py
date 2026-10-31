"""Resting limit orders (markets/resting.py): placement validation, the free fill pass (at/through the limit, not above it, stale prices, expiry, caps re-checked), the
per-day fill minimum, the portfolio text, the published section. Paper only, no model calls."""

from __future__ import annotations

from datetime import timedelta

import pytest
from test_markets_day import NOW, WORLD, _full_trust, _store, event, fake_get, raw  # noqa: F401  (autouse fixture re-exported so it applies here)

from algent_backend.markets import book, day, day_report, flags, resting, store, strategies
from algent_backend.markets.contracts import Decision, RestingOrder, Snapshot
from algent_backend.markets.day_prompt import Call
from algent_backend.markets.day_tools import Session

LATER = NOW + timedelta(hours=1)


def sess(sid="day", now=NOW, **kw):
    return Session(now=now, get=kw.pop("get", fake_get()), corpus=None, strategy=strategies.get(sid), **kw)


def rest(s, **kw):
    args = {"tool": "place_resting", "market": "a1", "way": "buy", "side": "yes", "limit_price": 0.45, "usd": 100.0, "hours": 10.0, "p_yes": 0.7, "reason": "Worth it at 45c."}
    return s.run(1, Call(**{**args, **kw}))


def tick(yes, at=NOW + timedelta(minutes=30), mid="a1"):
    store.append_snapshots([Snapshot(market_id=mid, at=at.isoformat(timespec="seconds"), p=yes)])


def state(oid=None, book_id="day"):
    o = resting.orders(book_id)
    return o[oid] if oid else list(o.values())[0]


# ── placement ────────────────────────────────────────────────────────────────────────────────────
def test_placing_records_an_open_order_with_a_capped_expiry_and_shows_in_the_portfolio():
    s = sess()
    ev = rest(s, hours=100.0)                                              # asks for far longer than the market lives (20 h)
    o = state()
    assert ev.ok and "RESTING order" in ev.result and ev.ref == o.id
    assert o.status == "open" and o.action == "buy_yes" and o.limit_price == 0.45 and o.usd == 100.0 and o.p_yes == 0.7 and o.book == "day"
    assert o.expires_at == (NOW + timedelta(hours=20)).isoformat(timespec="seconds")           # capped at the market's end
    assert store.markets()["a1"].origin == "day" and store.bot_forecasts("day") == [] and "a1" in s.forecast_log   # tracked, and its probability is a forecast
    text, _ = s.t_portfolio()
    assert "RESTING ORDERS" in text and f"R1 [{o.id}] BUY YES" in text and "limit 0.450" in text
    assert resting.cancel("day", o.id, NOW) .startswith("CANCELLED") and not resting.open_orders("day")


def test_placement_refusals(monkeypatch):
    s = sess()
    assert "expiry is required" in rest(s, hours=0).result
    assert "p_yes" in rest(s, p_yes=0).result
    assert "already reaches your limit" in rest(s, limit_price=0.55).result          # 0.50 + slippage is 0.51: use buy
    assert "limit is the all-in price" in rest(s, limit_price=1.2).result
    assert "needs side" in rest(s, side="").result
    assert "no position to sell" in rest(s, way="sell", side="", limit_price=0.9).result
    assert "NOT PLACED" in rest(s, market="far").result and "NOT PLACED" in rest(s, market="sp1").result       # same tradability rules as an order
    assert resting.orders() == {}
    assert rest(s).ok and "already have an open resting buy yes" in rest(s).result
    monkeypatch.setattr(flags, "RESTING_MAX_OPEN", 1)
    assert "limit is 1" in rest(s, market="a2", limit_price=0.1).result
    monkeypatch.setattr(flags, "RESTING_ENABLED", False)
    assert "switched off" in rest(sess(), market="a2", limit_price=0.1).result


def test_the_position_cap_is_checked_at_placement():
    s = sess()
    s.run(1, Call(tool="buy", market="a1", side="yes", usd=5000, p_yes=0.7, reason="x"))          # fills the 5% cap ($500)
    assert "refused by the book's limits" in rest(s, limit_price=0.3).result
    s2 = sess("delineation")
    ev = rest(s2, usd=1000.0, limit_price=0.3)                                                        # asks for $1000 against the $500 cap
    o = next(iter(resting.orders("delineation").values()))
    assert o.usd == 500.0 and "Trimmed" in ev.result and "position limit" in ev.result


# ── the fill pass ────────────────────────────────────────────────────────────────────────────────
def test_fills_at_or_through_the_limit_via_the_ledger_with_slippage_and_the_resting_tag():
    s = sess()
    rest(s)
    oid = state().id
    tick(0.44)                                                              # 0.44 + 0.01 slippage = 0.45 all-in: exactly at the limit
    rep = resting.run_pass(now=LATER, refresh=False)
    assert rep["filled"] == 1 and rep["open"] == 0
    d = [x for x in store.decisions("day") if x.tag == "resting"][0]
    assert d.action == "buy_yes" and d.order_id == oid and d.price == pytest.approx(0.45) and -d.cash_flow == pytest.approx(100.0) and d.ours == 0.7
    assert d.at == LATER.isoformat(timespec="seconds") and d.rationale == "Worth it at 45c." and d.model == "resting"
    o = state(oid)
    assert o.status == "filled" and o.fill_id == d.id and o.filled_at == d.at
    assert [e.status for e in store.resting_events("day")] == ["open", "filled"]           # append-only: the placement line is still there
    assert book.holdings(store.decisions("day"))["a1"].shares == pytest.approx(100 / 0.45, abs=1e-3)
    assert resting.run_pass(now=LATER, refresh=False)["filled"] == 0                        # a filled order is never filled twice
    tick(0.30, LATER)
    through = sess()
    rest(through, market="a2", limit_price=0.30, side="no", hours=5)
    tick(0.5, LATER + timedelta(minutes=5), "a2")                           # NO side price 0.5 + 0.01 = 0.51 > 0.30
    assert resting.run_pass(now=LATER + timedelta(minutes=10), refresh=False)["filled"] == 0


def test_no_fill_above_the_limit_and_a_stale_or_older_price_is_skipped(monkeypatch):
    rest(sess())
    tick(0.46)                                                              # 0.47 all-in > 0.45
    assert resting.run_pass(now=LATER, refresh=False)["filled"] == 0 and state().status == "open"
    tick(0.30, NOW - timedelta(minutes=10))                                 # cheap, but BEFORE the order was placed: not a price it can fill against
    assert resting.run_pass(now=LATER, refresh=False)["filled"] == 0 and state().status == "open"
    tick(0.30, NOW + timedelta(minutes=40))
    stale = resting.run_pass(now=NOW + timedelta(hours=flags.RESTING_MAX_SNAPSHOT_AGE_H + 1), refresh=False)
    assert stale["skipped_stale"] == 1 and stale["filled"] == 0 and state().status == "open"      # cheap but older than the max age: skipped, not guessed
    assert resting.run_pass(now=NOW + timedelta(hours=1), refresh=False)["filled"] == 1


def test_the_pass_refreshes_quotes_of_watched_markets_and_fills_from_them():
    rest(sess())
    world = {"events": [event("e1", ["politics"], [raw("a1", 20, bid=0.39, ask=0.41, q="Will the ceasefire hold?")])]}
    rep = resting.run_pass(now=LATER, get=fake_get(world))
    assert rep["filled"] == 1 and not rep["errors"]
    assert store.snapshots("a1")[-1].p == pytest.approx(0.40) and store.snapshots("a1")[-1].at == LATER.isoformat(timespec="seconds")
    rest(sess(now=LATER), market="a2", limit_price=0.1, hours=3)
    boom = resting.run_pass(now=LATER + timedelta(minutes=5), get=lambda url, params=None: (_ for _ in ()).throw(RuntimeError("down")))
    assert boom["errors"] and boom["filled"] == 0 and state(book_id="day").status == "filled"       # a failed fetch leaves the order open, never crashes


def test_expiry_and_a_closed_market_expire_the_order_with_a_reason_on_file():
    rest(sess(), hours=2)
    rep = resting.run_pass(now=NOW + timedelta(hours=3), refresh=False)
    o = state()
    assert rep["expired"] == 1 and o.status == "expired" and "expiry" in o.note and o.at == (NOW + timedelta(hours=3)).isoformat(timespec="seconds")
    rest(sess(now=LATER), market="a2", limit_price=0.1, hours=10)
    m = store.markets()["a2"]
    store.save_markets([m.model_copy(update={"status": "resolved", "outcome": "no"})])
    assert resting.run_pass(now=LATER + timedelta(minutes=1), refresh=False)["expired"] == 1
    assert [e.status for e in store.resting_events("day") if e.market_id == "a2"] == ["open", "expired"]


def test_a_cap_that_now_blocks_the_fill_cancels_it_and_a_trim_fills_smaller():
    s = sess()
    rest(s, usd=400.0, limit_price=0.30)
    s.run(1, Call(tool="buy", market="a1", side="yes", usd=300, p_yes=0.7, reason="x"))             # $300 of the $500 position cap is now used
    tick(0.20)
    rep = resting.run_pass(now=LATER, refresh=False)
    d = [x for x in store.decisions("day") if x.tag == "resting"][0]
    assert rep["filled"] == 1 and -d.cash_flow == pytest.approx(200.0) and any("position limit" in c for c in d.clips)       # trimmed exactly as an immediate order is
    s.run(1, Call(tool="buy", market="a1", side="yes", usd=5000, p_yes=0.7, reason="x"))            # now at the cap
    store.append_resting([RestingOrder(id="ro-x", book="day", market_id="a1", action="buy_yes", limit_price=0.4, usd=100.0, p_yes=0.7, placed_at=NOW.isoformat(timespec="seconds"),
                                                expires_at=(NOW + timedelta(hours=9)).isoformat(timespec="seconds"), at=NOW.isoformat(timespec="seconds"))])
    rep2 = resting.run_pass(now=LATER + timedelta(minutes=1), refresh=False)
    x = state("ro-x")
    assert rep2["cancelled"] == 1 and x.status == "cancelled" and "blocked at the fill" in x.note and "position limit" in x.note
    assert len([d for d in store.decisions("day") if d.tag == "resting"]) == 1                      # nothing was filled for it


def test_a_resting_sell_fills_when_the_bid_reaches_the_limit_and_books_the_realised_result():
    s = sess()
    s.run(1, Call(tool="buy", market="a1", side="yes", usd=200, p_yes=0.7, reason="x"))
    assert "no position" not in rest(s, way="sell", side="", limit_price=0.60, fraction=0.5, hours=8).result
    o = state()
    assert o.action == "sell" and o.fraction == 0.5 and o.usd == 0.0
    tick(0.55)                                                              # sells at 0.54 < 0.60: stays open
    assert resting.run_pass(now=LATER, refresh=False)["filled"] == 0
    tick(0.64, LATER)                                                       # sells at 0.63 >= 0.60
    assert resting.run_pass(now=LATER + timedelta(minutes=5), refresh=False)["filled"] == 1
    d = [x for x in store.decisions("day") if x.tag == "resting"][0]
    h = book.holdings(store.decisions("day"))["a1"]
    assert d.action == "sell" and d.price == pytest.approx(0.63) and d.realised > 0 and h.shares == pytest.approx(200 / 0.51 / 2, abs=1e-2)
    s2 = sess(now=LATER)
    assert "no open resting order" in s2.run(1, Call(tool="cancel_resting", order="nope")).result


def test_cancel_by_label_is_an_audited_transition():
    s = sess()
    rest(s)
    oid = state().id
    ev = s.run(2, Call(tool="cancel_resting", order="r1", reason="view changed"))
    assert "CANCELLED" in ev.result and state(oid).status == "cancelled" and "view changed" in state(oid).note
    assert [e.status for e in store.resting_events("day")] == ["open", "cancelled"]
    assert resting.run_pass(now=LATER, refresh=False)["open"] == 0


# ── counts as a fill ─────────────────────────────────────────────────────────────────────────────
def test_a_resting_fill_between_runs_counts_toward_the_days_minimum():
    world = {"events": [event("e9", ["politics"], [raw("h1", 8, q="Will talks start?")])]}
    st = strategies.get("hourly")
    assert st.min_fills_day == 1 and st.last_hour == 23
    rest(sess("hourly", get=fake_get(world)), market="h1", limit_price=0.4, hours=6)
    last = NOW.replace(hour=23, minute=25)
    owed = lambda ds=None: day._day_owes(st, sess("hourly", now=last, ds=ds))   # noqa: E731
    assert owed() == 1
    tick(0.30, NOW + timedelta(minutes=10), "h1")
    assert resting.run_pass(now=NOW + timedelta(hours=1), refresh=False)["filled"] == 1
    assert owed() == 0 and owed(ds=[]) == 0                                    # counted from the store, even for a session that loaded its ledger earlier
    assert day._fills(sess("hourly", now=last)) == 0                           # but it is not an order of THAT run (the per-run must-trade count is unchanged)


# ── the published section ────────────────────────────────────────────────────────────────────────
def test_the_section_lists_open_orders_and_recent_resting_fills():
    s = sess()
    rest(s)
    sec = day_report.section(None, "day")["resting"]
    assert len(sec["open"]) == 1 and sec["fills"] == []
    row = sec["open"][0]
    assert row["action"] == "buy_yes" and row["side"] == "yes" and row["limit"] == 0.45 and row["usd"] == 100.0 and row["now"] == pytest.approx(0.5) and row["question"]
    tick(0.40)
    resting.run_pass(now=LATER, refresh=False)
    sec = day_report.section(None, "day")["resting"]
    assert sec["open"] == [] and sec["fills"][0]["price"] == pytest.approx(0.41) and sec["fills"][0]["stake"] == 100.0 and sec["fills"][0]["order_id"]
    assert day_report.section(None, "fast")["resting"] == {"open": [], "fills": []}
    assert Decision(id="a", market_id="m", at="t", day="d", action="hold").order_id == ""
