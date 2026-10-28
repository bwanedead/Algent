"""Per-question error breakdown: deterministic tags from stored facts (stubbed models, temp stores)."""

from __future__ import annotations

from types import SimpleNamespace

import pytest

from algent_backend.experiment import branches, errors, policies, runner, sources, store
from algent_backend.experiment.contracts import Evidence, Question
from algent_backend.experiment.errors import tag_for

CUTOFF = "2026-03-10T12:00:00+00:00"


@pytest.fixture(autouse=True)
def stores(tmp_path, monkeypatch):
    monkeypatch.setenv("ALGENT_EXPERIMENT_STORE", str(tmp_path / "lab"))
    monkeypatch.setenv("ALGENT_MARKETS_STORE", str(tmp_path / "markets"))


def kw(**o):
    return dict(p=0.5, outcome=1, relevant=True, snapshot_overlap=True, structured=None, audit_leaks=0) | o


def test_tags_are_deterministic_reads_and_blank_when_nothing_fits():
    assert tag_for(**kw(p=0.05)) == "extreme/overconfident"
    assert tag_for(**kw(p=0.3, relevant=False, snapshot_overlap=True)) == "retrieval miss"
    assert tag_for(**kw(p=0.3, relevant=False, snapshot_overlap=False)) == "out-of-coverage"
    assert tag_for(**kw(p=0.1, relevant=False, snapshot_overlap=False)) == "extreme/overconfident; out-of-coverage"
    assert tag_for(**kw(p=0.4, outcome=0, relevant=False)) == "" and tag_for(**kw(p=0.3)) == ""                  # right-ish or wrong with evidence and moderate: blank, a human decides
    assert tag_for(**kw(p=0.01, outcome=0, relevant=False)) == "possible leak"                                  # sharp and right with no evidence used: maybe model memory
    assert tag_for(**kw(p=0.7, outcome=0, structured={"base_rate_pct": 75})) == "wrong base rate"             # a prior mind stayed near a base rate on the wrong side
    assert tag_for(**kw(p=0.7, outcome=0, structured={"base_rate_pct": 30})) == ""
    assert tag_for(**kw(p=0.6, audit_leaks=1)) == "possible leak" and tag_for(**kw(p=None)) == "invalid output"


def run(qid: str, docs, p: int, cited: list[str]):
    q = Question(id=qid, text=f"Will Aldoria sign a ceasefire {qid}?", rules="signed", cutoff=CUTOFF, closes_at="2026-03-31", reference={"market_p": 0.4, "market_p_at": "2026-03-10T06:00:00+00:00"})
    runner.save_question(q)
    b = branches.ensure("p0", policies.freeze_blind_forecaster())
    runner.run_controlled(q, [b], sources.ListSource(docs), lambda proto: (lambda t, r: (SimpleNamespace(probability_pct=p, rationale="r", cited=cited, evidence="sufficient"), 0.01)))
    store.write_once(f"resolutions/{qid}.json", {"question_id": qid, "outcome": "yes", "rule": "polymarket-outcome@1"})
    return q


def test_breakdown_shows_each_question_and_protocol_with_evidence_counts():
    d = [Evidence(id="d1", kind="daily", title="Aldoria ceasefire", body="Aldoria ceasefire talks", publish_time="2026-03-01", acquired_at="2026-03-01")]
    qs = [run("qa", d, 5, ["d1"]), run("qb", [], 10, []), run("qc", d, 30, [])]
    doc = {"id": "s1", "questions": [{"id": q.id} for q in qs] + [{"id": "missing"}]}
    rep = errors.breakdown(doc, resolve_now=False)
    by = {r["question"]: r for r in rep["rows"]}
    assert by["qa"]["tag"] == "extreme/overconfident" and by["qa"]["found_relevant"] is True and by["qa"]["n_evidence"] == 1 and by["qa"]["n_independent"] == 1
    assert by["qa"]["market_p"] == 0.4 and by["qa"]["brier"] == pytest.approx(0.9025) and by["qa"]["outcome"] == "yes"
    assert by["qb"]["tag"] == "extreme/overconfident; out-of-coverage" and by["qb"]["n_evidence"] == 0
    assert by["qc"]["tag"] == "retrieval miss"                                                                # evidence overlapped the question, nothing was used
    assert "extreme/overconfident" in errors.render(rep) and rep["unresolved"] == []


def test_cli_prints_tree_errors_and_audit(capsys):
    from algent_backend.cli.newsroom import lab as lab_cli
    from algent_backend.experiment import minds

    minds.freeze_prior()
    assert lab_cli.run_tree(SimpleNamespace(json=False)) == 0
    assert "p0b-prior" in capsys.readouterr().out
    d = [Evidence(id="d1", kind="daily", title="Aldoria ceasefire", body="Aldoria ceasefire talks", publish_time="2026-03-01", acquired_at="2026-03-01")]
    q = run("qx", d, 5, ["d1"])
    store.write_once("sets/s9/set.json", {"id": "s9", "questions": [{"id": q.id}]})
    store.append("sets/index.jsonl", {"id": "s9"})
    assert lab_cli.run_errors(SimpleNamespace(qset="latest", json=False)) == 0 and "qx" in capsys.readouterr().out
    assert lab_cli.run_audit(SimpleNamespace(target="qx", qset=None, corpus=None)) == 0 and '"clean"' in capsys.readouterr().out
