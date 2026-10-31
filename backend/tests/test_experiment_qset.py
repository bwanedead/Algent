"""The common question set and the controlled set run (stubbed models, temp stores)."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from types import SimpleNamespace

import pytest

from algent_backend.cli.newsroom import lab as lab_cli
from algent_backend.experiment import flags, qset, sources, store
from algent_backend.experiment.contracts import Evidence
from algent_backend.markets import research as rs
from algent_backend.markets import store as ms
from algent_backend.markets.contracts import Market, Snapshot

BASE = datetime(2026, 3, 20, 12, tzinfo=UTC)
DOCS = [Evidence(id="d1", kind="daily", source="t", title="talks", body="Talks stalled over monitors", publish_time="2026-01-01", acquired_at="2026-01-01")]


@pytest.fixture(autouse=True)
def stores(tmp_path, monkeypatch):
    monkeypatch.setenv("ALGENT_EXPERIMENT_STORE", str(tmp_path / "lab"))
    monkeypatch.setenv("ALGENT_MARKETS_STORE", str(tmp_path / "markets"))
    rows, snaps = [], []
    #            id    event  topic     outcome  days before BASE it resolved
    for i, (mid, ev, topic, out, back) in enumerate([("m1", "e1", "iran", "yes", 1), ("m2", "e1", "iran", "no", 2), ("m3", "e2", "iran", "no", 3), ("m4", "e3", "taiwan", "yes", 4),
                                                     ("m5", "e4", "ukraine", "no", 5), ("m6", "e5", "ukraine", "yes", 6), ("m7", "e6", "none", "yes", 7)]):
        res = BASE - timedelta(days=back)
        rows.append(Market(id=mid, event_id=ev, question=f"Will thing {mid} happen?", description="rules", end_date=res.isoformat(), status="resolved", outcome=out,
                           resolved_at=res.isoformat(), theaters=[] if topic == "none" else [topic]))
        if mid != "m7":                                                        # m7 has no price at its cutoff: not eligible
            snaps.append(Snapshot(market_id=mid, at=(res - timedelta(hours=49)).isoformat(), p=0.3))
    rows.append(Market(id="open1", question="still open", status="open"))
    ms.save_markets(rows)
    ms.append_snapshots(snaps)


def test_the_set_is_diverse_one_per_event_fixed_cutoff_and_versioned():
    doc = qset.build(min_n=3, max_n=4)
    ids = [e["id"] for e in doc["questions"]]
    assert len(ids) == 4 and doc["params"]["hours_before"] == 48 and not doc["short_of_target"]
    assert doc["topics"] == {"iran": 1, "taiwan": 1, "ukraine": 2} or max(doc["topics"].values()) <= 2         # round-robin across topics: no theme fills the set
    assert doc["skipped"]["same_event"] == 1 and doc["skipped"]["no_price_at_cutoff"] == 1
    qs = qset.questions_of(doc)
    assert all(q.common_set for q in qs)
    for q in qs:
        res = datetime.fromisoformat(ms.markets()[q.source.split(":", 1)[1]].resolved_at)
        assert datetime.fromisoformat(q.cutoff) == res - timedelta(hours=48) and q.reference["market_p"] == 0.3
    again = qset.build(min_n=3, max_n=4)
    assert again["id"] == doc["id"] and len(store.read_lines("sets/index.jsonl")) == 1          # same content, same version
    assert qset.build(min_n=3, max_n=3)["id"] != doc["id"] and qset.load("latest")["params"]["max_n"] == 3 and len(store.read_lines("sets/index.jsonl")) == 2
    assert qset.build()["short_of_target"] is True                                             # fewer than 20 eligible: it says so rather than padding


def asks(p: float, usd: float):
    def ask(task: str, role: str):
        return SimpleNamespace(probability=p, rationale="r", cited=["d1"]), usd

    return ask


def plan(task: str, role: str):
    return SimpleNamespace(queries=[rs.Query(market="M1", tool="search", arg="talks")]), 0.01


class Empty:
    def search(self, *a, **k):
        return []

    def entity(self, ref):
        return None


def test_run_set_runs_every_protocol_on_the_whole_set_under_a_total_cap_then_continues():
    doc = qset.build(min_n=3, max_n=3)
    src = sources.ListSource(DOCS)
    by_name = {"p0": asks(0.2, 0.08), "p0b": asks(0.8, 0.08)}
    from algent_backend.experiment import controls, policies
    p0, p0b = policies.freeze_blind_forecaster(), controls.freeze_production_research()
    table = {p0.id: by_name["p0"], p0b.id: by_name["p0b"]}
    dry = qset.run(doc, ["p0", "p0b"], src, lambda proto: table[proto.id], live=False, plan_ask_for=lambda pv: plan, corpus=Empty())
    assert dry["ran"] == [] and len(dry["not_run"]) == 6 and dry["max_usd_if_all_pending_run"] == pytest.approx(3 * (flags.RUN_CAP_USD + flags.RUN_CAP_USD + 0.04), abs=0.001)
    first = qset.run(doc, ["p0", "p0b"], src, lambda proto: table[proto.id], live=True, cap_usd=0.20, plan_ask_for=lambda pv: plan, corpus=Empty())
    assert first["stopped"] and 0 < len(first["ran"]) < 6 and first["spent_usd"] <= 0.20 + 0.1 and first["not_run"]
    n_first = len(first["ran"])
    second = qset.run(doc, ["p0", "p0b"], src, lambda proto: table[proto.id], live=True, cap_usd=5.0, plan_ask_for=lambda pv: plan, corpus=Empty())
    assert second["reused"] == n_first and len(second["ran"]) == 6 - n_first and not second["not_run"] and not second["stopped"]      # a finished run is never repeated
    third = qset.run(doc, ["p0", "p0b"], src, lambda proto: table[proto.id], live=True, cap_usd=5.0, plan_ask_for=lambda pv: plan, corpus=Empty())
    assert third["ran"] == [] and third["reused"] == 6 and third["spent_usd"] == 0

    board = qset.board(doc)
    assert board["n_questions"] == 3 and sorted(board["answered_by"].values()) == [3, 3] and not board["unresolved"]
    a, b = board["protocols"][p0.id], board["protocols"][p0b.id]
    assert a["n"] == 3 and a["abstained"] == 0 and a["brier_se"] is not None and a["log_se"] is not None and b["usd"] > a["usd"]        # cost beside the score; p0b pays its planner
    (pair,) = board["differences"].values()
    assert pair["n_shared"] == 3 and pair["se"] is not None and pair["log_se"] is not None and pair["brier_diff"] is not None


def test_frozen_trader_replays_over_a_forecast_protocols_runs_and_is_scored_apart():
    from algent_backend.experiment import controls, decision, policies
    doc = qset.build(min_n=3, max_n=3)
    p0b = controls.freeze_production_research()
    table = {policies.freeze_blind_forecaster().id: asks(0.2, 0.01), p0b.id: asks(0.8, 0.01)}
    qset.run(doc, ["p0", "p0b"], sources.ListSource(DOCS), lambda proto: table[proto.id], live=True, cap_usd=5.0, plan_ask_for=lambda pv: plan, corpus=Empty())
    trader = lambda task, role: (SimpleNamespace(decisions=[SimpleNamespace(market="M1", action="buy_yes", stake_usd=200, rationale="x", cited=[])]), 0.02)      # noqa: E731
    dry = decision.replay_set(doc, p0b, live=False, cap_usd=1.0)
    assert dry["decided"] == [] and len(dry["not_run"]) == 3
    out = decision.replay_set(doc, p0b, live=True, cap_usd=1.0, ask=trader)
    assert len(out["decided"]) == 3 and out["spent_usd"] == pytest.approx(0.06)
    assert decision.replay_set(doc, p0b, live=True, cap_usd=1.0, ask=trader)["decided"] == []          # stored decisions are reused, never repaid
    (row,) = decision.board()["protocols"].values()
    assert row["n"] == 3 and row["trades"] == 3 and row["staked"] == 600.0


def test_cli_builds_and_lists_sets(capsys):
    args = SimpleNamespace(limit=5, qset="build", min_n=2, hours=None)
    assert lab_cli.run_questions(args) == 0
    built = capsys.readouterr().out
    assert '"set"' in built and '"short_of_target": false' in built
    assert lab_cli.run_questions(SimpleNamespace(limit=5, qset="list", min_n=None, hours=None)) == 0
    assert '"n"' in capsys.readouterr().out


def test_multi_cutoff_set_gives_a_market_several_questions_but_one_market_per_event():
    res = lambda mid: datetime.fromisoformat(ms.markets()[mid].resolved_at)  # noqa: E731
    ms.append_snapshots([Snapshot(market_id="m1", at=(res("m1") - timedelta(hours=169)).isoformat(), p=0.4), Snapshot(market_id="m1", at=(res("m1") - timedelta(hours=13)).isoformat(), p=0.6),
                         Snapshot(market_id="m2", at=(res("m2") - timedelta(hours=13)).isoformat(), p=0.5),                            # m2 shares an event with m1
                         Snapshot(market_id="m4", at=(res("m4") - timedelta(hours=169)).isoformat(), p=0.2)])
    before = qset.build(min_n=3, max_n=4)
    dry = qset.build(hours_list=tuple(flags.SET_MULTI_HOURS), dry_run=True)
    assert dry["dry_run"] and not store.exists(f"sets/{dry['id']}/set.json")                       # a dry run stores nothing
    doc = qset.build(hours_list=tuple(flags.SET_MULTI_HOURS))
    assert doc["id"] == dry["id"] and doc["params"]["set_version"] == 2 and doc["params"]["hours_list"] == [168, 48, 12]
    srcs = [e["source"] for e in doc["questions"]]
    assert srcs.count("market:m1") == 3 and srcs.count("market:m4") == 2 and srcs.count("market:m3") == 1
    assert "market:m2" not in srcs                                                                  # same event as m1, which covers more cutoffs: the family counts once
    assert doc["n_markets"] == len(set(srcs)) == 5 and doc["by_hours_before"] == {"168": 2, "48": 5, "12": 1}
    assert doc["skipped"]["same_event"] == 1 and len({e["id"] for e in doc["questions"]}) == len(doc["questions"])
    for q in qset.questions_of(doc):
        mid = q.source.split(":", 1)[1]
        assert datetime.fromisoformat(q.cutoff) < res(mid) and q.reference["market_p"] is not None and q.common_set
    assert qset.load(before["id"])["params"] == before["params"] and "hours_list" not in before["params"]      # the old set is untouched
    capped = qset.build(hours_list=tuple(flags.SET_MULTI_HOURS), max_n=4, dry_run=True)
    assert len(capped["questions"]) == 4


def test_cli_dry_run_reports_the_yield_without_storing(capsys):
    args = SimpleNamespace(qset="build", min_n=None, hours=None, multi=True, dry_run=True, limit=20)
    assert lab_cli.run_questions(args) == 0
    out = capsys.readouterr().out
    assert '"dry_run": true' in out and '"n_markets"' in out and '"by_hours_before"' in out and not store.exists("sets/index.jsonl")


def test_an_older_question_with_the_same_id_and_different_content_is_left_alone():
    first = qset.build(hours_list=(48,))
    qid = first["questions"][0]["id"]
    old = store.read_json(f"questions/{qid}.json")
    store.path(f"questions/{qid}.json").unlink()
    store.write_once(f"questions/{qid}.json", {**old, "reference": {"market_p": None}})                # as stored by an older build
    again = qset.build(hours_list=(48,))
    assert qid not in {e["id"] for e in again["questions"]} and any(e["id"].startswith(qid + "-p") for e in again["questions"])
    assert store.read_json(f"questions/{qid}.json")["reference"] == {"market_p": None}
