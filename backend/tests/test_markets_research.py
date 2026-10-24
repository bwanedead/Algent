"""Corpus-only research for the market bots: tool execution against a fixture corpus (and its blindness to the market mirror), caps, the research trace, gap
dedupe and the daily fill cap, evidence metrics (withheld below the verdict threshold), the fast book (horizon filter, cadence, separate ledger) and the
published document's shape. Every model call is a stub; nothing touches the network."""

from __future__ import annotations

from datetime import UTC, date, datetime, timedelta
from types import SimpleNamespace

import pytest
from test_corpus_build import THR, record  # noqa: F401 - the fixture stores the corpus is built from

from algent_backend import corpus as corpus_build
from algent_backend.contracts import shapes, spec
from algent_backend.corpus.query import Corpus
from algent_backend.markets import book, books, flags, forecast, gaps, research, research_report, score, store, trader
from algent_backend.markets.contracts import Forecast, Market, Snapshot

NOW = datetime(2026, 10, 17, 12, 0, tzinfo=UTC)
TODAY = date(2026, 10, 17)


def seed(mid="m1", price=0.30, ours=0.60, end_days=60, countries=("IR",), fc_age_h=24.0):
    store.save_markets([Market(id=mid, question=f"Will Iran reopen the Strait of Hormuz ({mid})?", description="Resolves YES if tanker traffic resumes.",
                               url=f"https://polymarket.com/event/{mid}", end_date=(NOW + timedelta(days=end_days)).isoformat(), volume=1e5, theaters=[THR],
                               countries=list(countries))])
    store.append_snapshots([Snapshot(market_id=mid, at=(NOW - timedelta(hours=2)).isoformat(), p=price)])
    if ours is not None:
        store.append_forecast(Forecast(id=f"fc-{mid}", market_id=mid, made_at=(NOW - timedelta(hours=fc_age_h)).isoformat(), p=ours, rationale="Base rate is low."))


@pytest.fixture(autouse=True)
def _isolated_store(tmp_path, monkeypatch):
    monkeypatch.setenv("ALGENT_MARKETS_STORE", str(tmp_path / "ms"))
    monkeypatch.setenv("ALGENT_CORPUS_STORE", str(tmp_path / "no-corpus"))                   # no index unless a test builds one


def plan(*queries):
    """A planning stub: the same queries every round; records each task it was shown."""
    calls = []

    def ask(task, role=""):
        calls.append(task)
        return SimpleNamespace(queries=[SimpleNamespace(market=m, tool=t, arg=a, since="", kinds=[]) for m, t, a in queries]), 0.004

    ask.calls = calls
    return ask


@pytest.fixture()
def built(record, tmp_path, monkeypatch):  # noqa: F811
    monkeypatch.setenv("ALGENT_RETRIEVAL_STORE", str(tmp_path / "ret"))
    monkeypatch.delenv("DATABASE_URL", raising=False)
    seed("m1")                                              # the mirror, our forecast and a price are in the corpus too: research must not see them
    corpus_build.build(full=True)
    with Corpus.open() as c:
        yield c


# ── tools against the fixture corpus ─────────────────────────────────────────────────────────────
def test_every_tool_returns_citable_rows_and_none_of_them_is_the_market_mirror(built):
    q = research.Query
    for tool, arg in (("entity", "Iran"), ("about", "Iran"), ("search", "strait closed tanker traffic"), ("timeline", f"situation:{THR}"),
                      ("related", "Iran"), ("series", "pulse.*")):
        hits = research.run_query(built, q(tool=tool, arg=arg), today=TODAY)
        assert hits, tool
        assert all(h.id and h.title for h in hits), tool
        assert not any(h.id.startswith(("market:", "event:market:")) or "market.p" in h.id for h in hits), tool
    assert research.run_query(built, q(tool="entity", arg="Will Iran reopen the Strait of Hormuz (m1)?"), today=TODAY) == []     # a market entity is not offered
    assert research.run_query(built, q(tool="series", arg="market.p"), today=TODAY) == []
    assert not [h for h in research.run_query(built, q(tool="search", arg="Will Iran reopen Strait Hormuz m1"), today=TODAY) if "m1" in h.title]
    assert research.run_query(built, q(tool="entity", arg="zzzz nobody"), today=TODAY) == []


def test_research_caps_rounds_and_queries_and_ends_early_when_the_plan_is_empty(built):
    item = research.item_for("M1", store.markets()["m1"])
    many = plan(*[("M1", "search", f"tanker {i}") for i in range(10)])
    out = research.research([item], plan_ask=many, corpus=built, today=TODAY)["M1"]
    assert len(out.runs) <= flags.RESEARCH_MAX_ROUNDS * flags.RESEARCH_QUERIES_PER_ROUND and len(many.calls) <= flags.RESEARCH_MAX_ROUNDS
    assert "Already found for M1" in many.calls[-1] or len(many.calls) == 1                 # the second round is told what round one found
    none = plan()
    out2 = research.research([item], plan_ask=none, corpus=built, today=TODAY)["M1"]
    assert len(none.calls) == 1 and out2.runs == [] and out2.text == ""
    assert out.ids and set(out.ids) <= set(out.returned) and all(i in out.text for i in out.ids)


def test_a_failed_query_is_recorded_and_a_budget_refusal_propagates(built):
    item = research.item_for("M1", store.markets()["m1"])
    out = research.research([item], plan_ask=plan(("M1", "about", "Iran")), corpus=SimpleNamespace(about=lambda *a, **k: 1 / 0), today=TODAY)["M1"]
    assert out.runs and out.runs[0].error.startswith("ZeroDivisionError")

    class BudgetRefusedError(Exception):
        pass

    def refuse(task, role=""):
        raise BudgetRefusedError("halt")

    with pytest.raises(BudgetRefusedError):
        research.research([item], plan_ask=refuse, corpus=built, today=TODAY)


# ── a forecast: corpus-only evidence, citations, trace, gap ──────────────────────────────────────
def fc_ask(evidence="thin", gap="Hormuz insurance premiums", usd=0.02):
    seen = []

    def ask(task, role=""):
        seen.append(task)
        cited = [line[1:line.index("]")] for line in task.splitlines() if line.startswith("[")][:2] + ["invented:id"]
        return SimpleNamespace(probability=0.2, rationale="Base rate.", cited=cited, evidence=evidence, gap_topic=gap, gap_why="to size the risk"), usd

    ask.seen = seen
    return ask


def test_a_forecast_reads_only_corpus_results_cites_only_shown_ids_and_leaves_a_trace_and_a_gap(built):
    seed("f1", ours=None)
    ask = fc_ask()
    out = forecast.run(ask=ask, now=NOW, plan_ask=plan(("M1", "search", "strait closed tanker traffic"), ("M1", "entity", "Iran")), corpus=built, record={})
    assert out["made"] == 1 and out["usd"] == pytest.approx(0.02 + 2 * 0.004)                  # planning is part of the forecast's cost (two rounds)
    f = store.forecasts()[-1]
    assert f.book == "daily" and f.evidence == "thin" and "invented:id" not in f.evidence_ids and len(f.evidence_ids) == 2
    assert f.prompt_version == forecast.PROMPT_VERSION_RESEARCH and f.hours_to_end == pytest.approx(60 * 24)
    assert "WHAT THE DESK KNOWS" in ask.seen[0] and "theater:" not in ask.seen[0]                 # not evidence.py's blocks
    t = store.traces()[-1]
    assert t.kind == "forecast" and t.mode == "corpus" and t.ref == f.id and t.queries and t.cited_ids == f.evidence_ids
    assert set(t.cited_ids) <= set(t.shown_ids) <= set(t.returned_ids) and t.plan_usd == pytest.approx(0.008) and t.usd == pytest.approx(0.028) and t.tokens > 0
    g = store.gaps()[-1]
    assert g.topic == "Hormuz insurance premiums" and g.market_id == "f1" and g.kind == "forecast"


def test_without_a_corpus_the_forecast_falls_back_to_the_desk_blocks_and_says_so(record, tmp_path, monkeypatch):  # noqa: F811
    monkeypatch.setenv("ALGENT_CORPUS_STORE", str(tmp_path / "no-corpus"))
    seed("m1", ours=None)
    out = forecast.run(ask=fc_ask(), now=NOW, plan_ask=plan(), index=None, record={})
    assert out["made"] == 1
    f, t = store.forecasts()[-1], store.traces()[-1]
    assert t.mode == "base-fallback" and f.evidence == "" and f.prompt_version == forecast.PROMPT_VERSION and not store.gaps()     # no verdict, no gap without research


def test_research_switched_off_uses_the_old_evidence_path(built, monkeypatch):
    monkeypatch.setattr(flags, "RESEARCH_ENABLED", False)
    seed("f1", ours=None)
    forecast.run(ask=fc_ask(), now=NOW, record={}, index=None)
    assert store.traces()[-1].mode == "base" and store.forecasts()[-1].evidence == ""


# ── the trader: batch research, citations, trace, gap ────────────────────────────────────────────
def trade_ask(evidence="gap"):
    def ask(task, role=""):
        labels = [ln.split()[1] for ln in task.splitlines() if ln.startswith("### ")]
        ids = [ln[1:ln.index("]")] for ln in task.splitlines() if ln.startswith("[")][:3]
        calls = [SimpleNamespace(market=lab, action="hold", stake_usd=0.0, rationale="Stand aside.", cited=[*ids, "nope"], evidence=evidence,
                                 gap_topic="Omani mediation channel", gap_why="would change the odds") for lab in labels]
        return SimpleNamespace(decisions=calls), 0.05

    return ask


def test_a_trade_decision_cites_corpus_items_and_a_thin_batch_files_a_gap(built):
    out = trader.run(ask=trade_ask(), now=NOW, plan_ask=plan(("M1", "about", "Iran"), ("M1", "search", "strait tanker")), corpus=built)
    assert out["decided"] == 1
    d = store.decisions()[-1]
    assert d.book == "daily" and d.evidence == "gap" and d.evidence_ids and "nope" not in d.evidence_ids and d.prompt_version == "trader-v2"
    assert d.usd == pytest.approx(0.05 + 0.008)
    t = store.traces()[-1]
    assert t.kind == "trade" and t.ref == d.id and t.cited_ids == d.evidence_ids and t.queries
    assert store.gaps()[-1].kind == "trade" and store.gaps()[-1].topic == "Omani mediation channel"
    pos = trader_positions_after_a_buy()
    assert pos[0]["trail"] and pos[0]["evidence"] == "sufficient"


def trader_positions_after_a_buy():
    from algent_backend.markets import trader_report

    ask = trade_ask("sufficient")

    def buy(task, role=""):
        out, usd = ask(task, role)
        for c in out.decisions:
            c.action, c.stake_usd = "buy_yes", 100.0
        return out, usd

    trader.run(ask=buy, now=NOW + timedelta(days=1), plan_ask=plan(("M1", "about", "Iran")), corpus=Corpus.open())
    return trader_report.open_positions(store.decisions())


# ── gaps: dedupe, ranking, the daily cap, parking ────────────────────────────────────────────────
def test_near_duplicate_asks_cluster_and_the_top_gap_is_the_most_asked():
    gaps.record("Hormuz tanker insurance premiums", "a", market_id="m1", at="2026-10-16T10:00:00+00:00")
    gaps.record("insurance premiums for Hormuz tankers", "b", market_id="m2", at="2026-10-16T11:00:00+00:00")
    gaps.record("Omani mediation channel", "c", market_id="m1", at="2026-10-16T12:00:00+00:00")
    assert gaps.record("Hormuz tanker insurance premiums", "again", market_id="m1", at="2026-10-16T13:00:00+00:00") is None       # same market, same ask: once
    assert gaps.record("the", "stopwords only", market_id="m1") is None
    top = gaps.top(5, NOW)
    assert [(g["asks"], g["status"]) for g in top] == [(2, "open"), (1, "open")] and {m["market_id"] for m in top[0]["markets"]} == {"m1", "m2"}


def test_the_daily_fill_obeys_its_dollar_and_run_caps_and_never_repeats_a_filled_topic(monkeypatch):
    for i, t in enumerate(["Hormuz tanker insurance premiums", "Omani mediation channel", "Houthi missile inventory", "Kharg terminal throughput"]):
        for m in range(4 - i):
            gaps.record(t, "why", market_id=f"m{m}", at=f"2026-10-16T1{i}:00:00+00:00")
    ran = []

    def runner(topic, why):
        ran.append((topic, why))
        return {"ok": True}

    monkeypatch.setattr(flags, "GAP_FILL_MAX_PER_DAY", 5)
    r = gaps.fill(now=NOW, runner=runner)
    assert r["ran"] == 2 and r["usd"] == pytest.approx(0.5) and "day budget" in r["stopped"]                        # 0.50 / 0.25 per run
    assert [t for t, _ in ran] == ["Hormuz tanker insurance premiums", "Omani mediation channel"]                    # most-asked first
    assert gaps.fill(now=NOW, runner=runner)["ran"] == 0 and len(ran) == 2                                          # same day: nothing left
    nxt = gaps.fill(now=NOW + timedelta(days=1), runner=runner)
    assert [t["topic"] for t in nxt["topics"]] == ["Houthi missile inventory", "Kharg terminal throughput"]          # the filled two are inside the refill window
    assert {g["status"] for g in gaps.top(4, NOW + timedelta(days=1))} == {"filled"}


def test_a_topic_that_fails_twice_is_parked_and_the_switch_stops_everything(monkeypatch):
    gaps.record("Kharg terminal throughput", "why", market_id="m1", at="2026-10-16T10:00:00+00:00")
    calls = []

    def bad(topic, why):
        calls.append(topic)
        return {"ok": False, "note": "exit 1"}

    for d in range(3):
        gaps.fill(now=NOW + timedelta(days=d), runner=bad)
    assert len(calls) == 2 and gaps.top(1, NOW)[0]["status"] == "tried"
    monkeypatch.setattr(flags, "GAP_FILL_ENABLED", False)
    assert "switched off" in gaps.fill(now=NOW + timedelta(days=9), runner=bad)["stopped"]


def test_the_gap_run_is_a_stamped_capped_profile_vector():
    v = gaps.gap_vector("Omani mediation channel", "to size it")
    assert v["requested_by"] == "markets" and v["cost_cap_usd"] == flags.GAP_FILL_RUN_CAP_USD and v["id"].startswith("gap_") and v["title"] == "Omani mediation channel"
    from algent_backend.agent_system.agents.research import loop
    assert loop._run_cap(v, 1.0) == flags.GAP_FILL_RUN_CAP_USD and loop._run_cap({"cost_cap_usd": 9}, 1.0) == 1.0 and loop._run_cap({}, 1.0) == 1.0


# ── traces: bounded retention; metrics: coverage, and the accuracy split withheld until n is enough ──
def test_old_traces_are_pruned_and_nothing_else(built):
    seed("f1", ours=None)
    forecast.run(ask=fc_ask(), now=NOW, plan_ask=plan(("M1", "entity", "Iran")), corpus=built, record={})
    n_f = len(store.forecasts())
    assert store.prune_traces(NOW + timedelta(days=flags.TRACE_KEEP_DAYS - 1)) == 0
    assert store.prune_traces(NOW + timedelta(days=flags.TRACE_KEEP_DAYS + 1)) == 1 and store.traces() == [] and len(store.forecasts()) == n_f and store.gaps()


def pair(evidence, cited, p, outcome, market_p=None):
    f = SimpleNamespace(evidence=evidence, evidence_ids=["a"] * cited, hours_to_end=30.0, made_at=NOW.isoformat())
    return SimpleNamespace(forecast=f, ours=p, outcome=outcome, market_p=market_p, market=SimpleNamespace(end_date="", resolved_at=""))


def test_coverage_and_citations_count_rated_decisions():
    fcs = [Forecast(id=f"f{i}", market_id="m", made_at=NOW.isoformat(), p=0.5, evidence=e, evidence_ids=["a"] * n) for i, (e, n) in enumerate([("sufficient", 3), ("thin", 1), ("", 4)])]
    c = research_report.coverage(fcs, [])
    assert (c["rated"], c["sufficient"], c["thin"], c["share_sufficient"]) == (2, 1, 1, 0.5)
    assert research_report.citations(fcs, [])["mean"] == 2.0                                                          # the unrated (pre-research) forecast is not counted


def test_accuracy_by_richness_is_withheld_until_a_group_is_large_enough(monkeypatch):
    ps = [pair("sufficient", 4, 0.8, 1, 0.6), pair("sufficient", 3, 0.7, 1, 0.5), pair("thin", 1, 0.5, 0, 0.5), pair("", 5, 0.9, 1, 0.9)]
    a = research_report.accuracy_split(ps)
    rich, thin = a["forecasts"]
    assert (rich["n"], thin["n"]) == (2, 1) and not rich["shown"] and rich["brier_ours"] is None and not a["trades"][0]["shown"]       # the pre-research pair is ignored
    monkeypatch.setattr(flags, "MIN_RESOLVED_FOR_VERDICT", 2)
    rich = research_report.accuracy_split(ps)["forecasts"][0]
    assert rich["shown"] and rich["brier_ours"] == pytest.approx(0.065) and rich["brier_market"] == pytest.approx(0.205) and rich["skill"] > 0


# ── the fast book ────────────────────────────────────────────────────────────────────────────────
def test_the_fast_book_only_sees_markets_inside_its_horizon():
    for mid, days in (("soon", 3), ("later", 20), ("now", 0.1)):
        seed(mid, end_days=days)
    ms = store.markets()
    assert [books.FAST.in_scope(ms[m], NOW) for m in ("soon", "later", "now")] == [True, False, False]
    assert [m.id for m, _ in trader.candidates(NOW, "fast")] == ["soon"]
    assert {m.id for m, _ in trader.candidates(NOW, "daily")} == {"soon", "later", "now"}
    assert [m.id for m in forecast.candidates(NOW, "fast")] == []                                                   # soon has a 24 h-old forecast, inside FAST_FORECAST_MAX_AGE_H
    seed("old", end_days=3, fc_age_h=48)                                                                              # a forecast older than FAST_FORECAST_MAX_AGE_H is stale
    assert [m.id for m in forecast.candidates(NOW, "fast")] == ["old"]


def test_the_fast_book_has_its_own_ledger_cadence_cap_and_equity_curve(built, monkeypatch):
    seed("soon", end_days=3)
    ask = trade_ask("sufficient")

    def buy(task, role=""):
        out, usd = ask(task, role)
        for c in out.decisions:
            c.action, c.stake_usd = "buy_yes", 200.0
        return out, usd

    pl = plan(("M1", "about", "Iran"))
    first = trader.run(ask=buy, now=NOW, book_name="fast", plan_ask=pl, corpus=built)
    assert first["decided"] == 1 and first["filled"] == 1 and first["book"] == "fast"
    assert len(store.decisions("fast")) == 1 and store.decisions("fast")[0].book == "fast" and not [d for d in store.decisions() if d.market_id == "soon"]   # daily ledger untouched
    assert book.cash(store.decisions()) == flags.BANKROLL and book.cash(store.decisions("fast")) < flags.BANKROLL
    assert trader.run(ask=buy, now=NOW + timedelta(hours=1), book_name="fast", plan_ask=pl, corpus=built)["candidates"] == 0       # decided inside FAST_RECHECK_H
    assert trader.run(ask=buy, now=NOW + timedelta(hours=4), book_name="fast", plan_ask=pl, corpus=built)["decided"] == 1          # the next 4-hourly slot asks again
    monkeypatch.setattr(flags, "FAST_MAX_USD_PER_RUN", 0.05)
    monkeypatch.setattr(flags, "TRADE_BATCH", 1)
    seed("soon2", end_days=2)
    seed("soon3", end_days=2.5)
    capped = trader.run(ask=buy, now=NOW + timedelta(hours=9), book_name="fast", plan_ask=pl, corpus=built)
    assert capped["decided"] == 1 and "run budget" in capped["stopped"]                                              # one batch spent the run's money; the rest wait for the next slot
    pts = book.mark(NOW + timedelta(hours=9))
    assert {p.book for p in pts} == {"trader", "rule", "fast"}
    sec = research_report.fast_section()
    assert sec["horizon_days"] == flags.FAST_HORIZON_DAYS and sec["curve"][-1]["trader"] is not None and sec["summary"]["open"] == 1


def test_the_fast_forecast_pass_is_blind_capped_per_run_and_books_to_the_fast_ledger(built, monkeypatch):
    monkeypatch.setattr(flags, "FAST_MAX_USD_PER_RUN", 1.0)
    for i in range(6):
        seed(f"s{i}", end_days=2 + i * 0.5, ours=None)
    out = forecast.run(ask=fc_ask(evidence="sufficient", gap=""), now=NOW, book="fast", plan_ask=plan(("M1", "entity", "Iran")), corpus=built, record={})
    assert out["made"] == flags.FAST_FORECASTS_PER_RUN and all(f.book == "fast" for f in store.forecasts() if f.market_id.startswith("s"))
    assert forecast.today_spend(store.forecasts(), NOW.date().isoformat(), "daily")[0] == 0
    monkeypatch.setattr(flags, "FAST_MAX_USD_PER_RUN", 0.05)                                                          # forecasts may take half a run's money
    again = forecast.run(ask=fc_ask(evidence="sufficient", gap=""), now=NOW + timedelta(hours=4), book="fast", plan_ask=plan(("M1", "entity", "Iran")), corpus=built, record={})
    assert again["made"] <= 1


# ── the published document ───────────────────────────────────────────────────────────────────────
def test_the_track_record_carries_the_new_sections_and_keeps_its_contract(built):
    seed("f1", ours=None)
    forecast.run(ask=fc_ask(), now=NOW, plan_ask=plan(("M1", "search", "tanker")), corpus=built, record={})
    seed("soon", end_days=3)
    trader.run(ask=trade_ask(), now=NOW, book_name="fast", plan_ask=plan(("M1", "about", "Iran")), corpus=built)
    doc = score.track_record()
    assert spec.validate(doc, shapes.SHAPES["ohmega.track-record"]) == []
    assert doc["schema"] == "ohmega.track-record/2"                                                                # additive: no major bump
    e = doc["evidence"]
    assert e["coverage"]["rated"] >= 2 and e["tools"]["queries"] >= 2 and e["top_gaps"] and e["caps"]["gap_fill_usd_per_day"] == flags.GAP_FILL_USD_PER_DAY
    assert doc["fast"]["every_hours"] == flags.FAST_EVERY_H and doc["horizons"]["books"]["fast"]["positions"] == 0
    assert all(g["shown"] is False for g in e["accuracy"]["forecasts"])                                           # nothing resolved: counts only
