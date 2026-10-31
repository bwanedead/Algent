"""The gap research loop (markets/gap_loop.py): linking a fill to its profile (recorded id and the retroactive search), each verdict, the too-early rule for the
edge, the refill rule (once, brief quotes the re-asks, daily caps respected) and the published block. No model call; nothing touches the network."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest

from algent_backend.markets import flags, gap_loop, gaps, research_report, store
from algent_backend.markets.contracts import BotForecast, Forecast, Gap, GapFill, Market, Trace

NOW = datetime(2026, 10, 20, 12, 0, tzinfo=UTC)
TOPIC = "Strait of Hormuz tanker traffic status"
PID = "prof_gap_strait_of_hormuz_tanker_traffic_status"


def ago(days: float) -> str:
    return (NOW - timedelta(days=days)).isoformat(timespec="seconds")


@pytest.fixture(autouse=True)
def _isolated_store(tmp_path, monkeypatch):
    monkeypatch.setenv("ALGENT_MARKETS_STORE", str(tmp_path / "ms"))
    monkeypatch.setenv("ALGENT_PROFILE_STORE", str(tmp_path / "no-profiles"))


def ask(mid, days, topic=TOPIC, why="", question=""):
    store.append_gaps([Gap(id=f"g-{mid}-{days}-{topic[:5]}", at=ago(days), day=ago(days)[:10], topic=topic, why=why, market_id=mid, question=question)])


def fill(days=10.0, ok=True, topic=TOPIC, pid=PID, markets=("m1",), refill=False, usd=0.25):
    f = GapFill(id=f"f-{topic[:6]}-{days}", at=ago(days), day=ago(days)[:10], key=gaps.cluster_key(topic), topic=topic, asks=1, markets=list(markets), ok=ok, usd=usd,
                profile_id=pid if ok else "", refill=refill)
    store.append_gap_fills([f])
    return f


_n = [0]


def decision(mid, days, cited=(), rating="thin"):
    _n[0] += 1
    store.append_forecast(Forecast(id=f"fc{_n[0]}", market_id=mid, made_at=ago(days), p=0.4, evidence=rating, evidence_ids=list(cited)))
    return f"fc{_n[0]}"


def row(f=None):
    return gap_loop.assess(f or store.gap_fills()[0], gap_loop.load([]), NOW)


def cands(now=NOW):
    return gap_loop.refill_candidates(now, gap_loop.load([]))


# ── linking ──────────────────────────────────────────────────────────────────────────────────────
def prof(pid, title=TOPIC, by="markets", days=10.0):
    return {"id": pid, "title": title, "requested_by": by, "generated_at": ago(days - 0.02)}


def test_a_recorded_profile_id_links_and_one_missing_from_a_readable_store_falls_back_to_the_search():
    f = fill()
    assert gap_loop.link(f, []) == PID                                   # no store here: the recorded id is trusted
    assert gap_loop.link(f, [prof(PID)]) == PID
    assert gap_loop.link(f, [prof("prof_other_name")]) == "prof_other_name"      # the recorded id is not in the store; the run's profile is found by search


def test_old_fills_link_retroactively_by_requester_time_and_topic_and_otherwise_say_unlinked():
    f = fill(pid="")
    assert gap_loop.link(f, [prof("prof_a")]) == "prof_a"
    assert gap_loop.link(f, [prof("prof_a", by="")]) == ""                                     # not a markets request
    assert gap_loop.link(f, [prof("prof_a", days=3.0)]) == ""                                  # written days after the run
    assert gap_loop.link(f, [prof("prof_a", title="Wheat export quotas in Russia")]) == ""      # another topic
    assert gap_loop.link(f, [prof("prof_far", days=10.2), prof("prof_near", days=10.0)]) == "prof_near"
    assert gap_loop.link(f, []) == ""


def test_ids_that_come_from_one_profile_match_exactly():
    assert all(gap_loop._ours(i, "prof_a") for i in ("profile:prof_a", "claim:prof_a:c1", "profile-timeline:prof_a:2026-01-01:x"))
    assert not any(gap_loop._ours(i, "prof_a") for i in ("profile:prof_ab", "claim:prof_ab:c1", "daily:2026-10-01:x"))


# ── verdicts ─────────────────────────────────────────────────────────────────────────────────────
def test_cited_after_the_fill_is_answered_and_counts_returned_and_cited_separately():
    ask("m1", 12)
    fill(10)
    a = decision("m1", 5, cited=[f"claim:{PID}:c1"], rating="sufficient")
    b = decision("m1", 4, cited=["daily:x"])
    store.append_traces([Trace(id="t1", at=ago(5), kind="forecast", market_id="m1", ref=a, returned_ids=[f"claim:{PID}:c1"], cited_ids=[f"claim:{PID}:c1"]),
                         Trace(id="t2", at=ago(4), kind="forecast", market_id="m1", ref=b, returned_ids=[f"profile:{PID}"])])
    r = row()
    assert (r["verdict"], r["cited_after"], r["returned_after"], r["decisions_after"]) == ("answered", 1, 2, 2)
    assert r["evidence_after"]["sufficient"] == 1 and r["evidence_before"]["rated"] == 0


def test_used_by_no_one_is_unused_but_only_once_there_was_a_chance():
    ask("m1", 12)
    fill(10)
    assert row()["verdict"] == "too early"                               # nothing has been decided on its markets since
    decision("m1", 5, cited=["daily:x"])
    assert row()["verdict"] == "unused"
    ask("m2", 1, topic="Gold price")
    f = fill(1, topic="Gold price", pid="prof_gold", markets=("m2",))
    decision("m2", 0.5)
    assert row(f)["verdict"] == "too early"                              # a day old: inside LOOP_SETTLE_DAYS


def test_reasks_after_the_fill_mean_asked_again_even_when_the_profile_was_cited():
    ask("m1", 12)
    fill(10)
    ask("m2", 6, topic="Hormuz tanker traffic strait status")
    assert row()["verdict"] == "too early"                               # one re-ask is not enough, and nothing was decided yet
    ask("m3", 3)
    decision("m2", 2, cited=[f"profile:{PID}"])
    r = row()
    assert (r["verdict"], r["reasks_before"], r["reasks_after"], r["cited_after"]) == ("asked again", 1, 2, 1)


def test_a_fill_with_no_findable_profile_is_unlinked_not_unused():
    ask("m1", 12)
    fill(10, pid="")
    decision("m1", 5)
    r = row()
    assert r["verdict"] == "unlinked" and r["cited_after"] is None


# ── accuracy: shown only when each side holds enough resolved forecasts ───────────────────────────
def bot_fcs(mid, days, n, p, market):
    store.append_bot_forecasts([BotForecast(id=f"b-{mid}-{days}-{i}-{p}", strategy="s", run_id=f"r{i}{p}", market_id=mid, at=ago(days - i * 0.001), day=ago(days)[:10], p=p,
                                            market=market) for i in range(n)])


def resolve(mid, outcome="yes"):
    store.save_markets([Market(id=mid, question="q", description="", url="u", end_date=ago(1), volume=1.0, status="resolved", outcome=outcome, resolved_at=ago(1))])


def test_edge_is_withheld_until_both_sides_hold_the_minimum_and_then_is_market_brier_minus_ours(monkeypatch):
    monkeypatch.setattr(flags, "MIN_RESOLVED_FOR_VERDICT", 5)
    ask("m1", 12)
    fill(10)
    resolve("m1")
    bot_fcs("m1", 20, 5, p=0.5, market=0.5)                              # before: bot = market -> edge 0
    bot_fcs("m1", 5, 4, p=0.9, market=0.5)                               # after: only 4 so far
    e = row()["edge"]
    assert (e["shown"], e["n_before"], e["n_after"], e["before"], e["after"]) == (False, 5, 4, None, None)
    bot_fcs("m1", 4, 1, p=0.9, market=0.5)
    e = row()["edge"]
    assert e["shown"] and e["before"] == 0.0 and e["after"] == pytest.approx(0.24)      # (0.5-1)^2 - (0.9-1)^2


def test_edge_ignores_markets_not_forecast_on_both_sides_of_the_fill(monkeypatch):
    monkeypatch.setattr(flags, "MIN_RESOLVED_FOR_VERDICT", 1)
    ask("m1", 12)
    fill(10)
    resolve("m1")
    bot_fcs("m1", 20, 3, p=0.5, market=0.5)                              # only before
    assert row()["edge"]["shown"] is False


# ── the refill rule ──────────────────────────────────────────────────────────────────────────────
def asked_again(topic=TOPIC, days=5.0, qs=("Will tankers transit Hormuz by Nov 30?", "Will Iran close the strait?")):
    ask("a1", days + 6, topic=topic)
    fill(days, topic=topic, pid="prof_x")
    ask("a2", days - 2, topic=topic, why="No data on insurance rates", question=qs[0])
    ask("a3", days - 3, topic=topic, why="Who escorts convoys", question=qs[1])


def test_an_asked_again_cluster_is_refilled_once():
    asked_again()
    out = gaps.fill(now=NOW, runner=lambda t, w: {"ok": True, "profile_id": "prof_x"})
    assert out["ran"] == 1 and out["topics"][0]["refill"] is True
    last = store.gap_fills()[-1]
    assert last.refill and last.profile_id == "prof_x"
    ask("a4", 0.1)
    ask("a5", 0.05)
    assert cands(NOW + timedelta(days=1)) == []                          # never a second refill, however it went


def test_an_event_already_past_is_not_refilled():
    asked_again()
    store.save_markets([Market(id=m, question="q", description="", url="u", end_date=ago(1), volume=1.0, status="open") for m in ("a1", "a2", "a3")])
    assert cands() == []                                                 # every linked market has ended
    store.save_markets([Market(id="a2", question="q", description="", url="u", end_date=ago(-9), volume=1.0, status="open")])
    assert len(cands()) == 1                                             # one is still running: the ask is live


def test_a_past_event_is_dropped_by_its_dated_cues_when_no_market_is_held():
    topic = "Likud polling Oct 12"
    asked_again(topic=topic, qs=("Will Likud win the vote held Oct 12?", "Likud seats after the Oct 12 election"))
    assert cands() == []


def test_a_failed_refill_is_also_the_one_refill():
    asked_again()
    gaps.fill(now=NOW, runner=lambda t, w: {"ok": False})
    assert cands(NOW + timedelta(days=1)) == []


def test_the_refill_brief_names_what_was_left_unanswered():
    asked_again()
    [c] = cands()
    assert c.refill and c.asks == 2 and "insurance rates" in c.why and "Who escorts convoys" in c.why and "Will tankers transit" in c.why
    seen = []
    gaps.fill(now=NOW, runner=lambda t, w: seen.append(w) or {"ok": False})
    assert seen and "insurance rates" in seen[0]
    assert gaps.gap_vector(TOPIC, seen[0])["thesis"] == seen[0]


def test_one_reask_or_a_fill_outside_the_refill_window_is_not_eligible():
    ask("a1", 12)
    fill(10)
    ask("a2", 5)
    assert cands() == []
    ask("a3", 4)
    assert len(cands()) == 1
    assert cands(NOW + timedelta(days=flags.GAP_REFILL_DAYS)) == []      # past the window the ordinary path takes over


def test_refills_share_the_daily_caps(monkeypatch):
    asked_again()
    asked_again("Wheat export quotas Russia grain", days=6.0)
    monkeypatch.setattr(flags, "GAP_FILL_MAX_PER_DAY", 1)
    assert gaps.fill(now=NOW, runner=lambda t, w: {"ok": True})["ran"] == 1
    assert gaps.fill(now=NOW, runner=lambda t, w: {"ok": True})["ran"] == 0
    monkeypatch.setattr(flags, "GAP_FILL_MAX_PER_DAY", 5)
    monkeypatch.setattr(flags, "GAP_FILL_USD_PER_DAY", 0.30)             # the 0.25 estimate leaves no room for a second run in a day
    nxt = NOW + timedelta(days=1)
    assert gaps.fill(now=nxt, runner=lambda t, w: {"ok": True})["ran"] == 1
    assert gaps.fill(now=nxt, runner=lambda t, w: {"ok": True})["ran"] == 0


# ── the published block ──────────────────────────────────────────────────────────────────────────
def test_the_block_totals_every_fill_and_lists_the_newest_rows_capped(monkeypatch):
    monkeypatch.setattr(flags, "LOOP_ROWS_SHOWN", 1)
    ask("m1", 12)
    fill(10)
    fill(8, ok=False, topic="Gold price")
    asked_again("Wheat export quotas Russia grain", days=4.0)
    b = gap_loop.block(NOW, gap_loop.load([]))
    assert (b["fills"], b["failed"], b["asked_again"], b["usd"]) == (2, 1, 1, 0.75)
    assert [r["topic"] for r in b["rows"]] == ["Wheat export quotas Russia grain"]
    assert sum(b[k] for k in ("answered", "unused", "asked_again", "too_early", "unlinked")) == b["fills"]


def test_the_evidence_section_carries_the_loop_block():
    ask("m1", 12)
    fill(10)
    assert research_report.section([], NOW)["loop"]["fills"] == 1
