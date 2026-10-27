"""Replay integrity audit and the leak fixes it found (stubbed models, temp stores, a tiny sqlite corpus)."""

from __future__ import annotations

import json
import sqlite3
from types import SimpleNamespace

import pytest

from algent_backend.experiment import audit, branches, controls, cutoff_corpus, runner, sources, store
from algent_backend.experiment.contracts import Evidence
from algent_backend.markets import research as rs
from algent_backend.markets import store as ms
from algent_backend.markets.contracts import Market, Snapshot

CUTOFF = "2026-03-10T12:00:00+00:00"


@pytest.fixture(autouse=True)
def stores(tmp_path, monkeypatch):
    monkeypatch.setenv("ALGENT_EXPERIMENT_STORE", str(tmp_path / "lab"))
    monkeypatch.setenv("ALGENT_MARKETS_STORE", str(tmp_path / "markets"))
    monkeypatch.setenv("ALGENT_ACQUISITION_STORE", str(tmp_path / "acq"))
    base = dict(id="m1", question="Will Aldoria and Brevia sign a ceasefire?", end_date="2026-03-31T00:00:00+00:00", event_id="e1")
    ms._append("markets.jsonl", [Market(**base, description="Resolves YES if signed.", updated_at="2026-03-01T00:00:00+00:00"),         # the rules as they stood before the cutoff
                                 Market(**base, description="Resolves YES if signed. UPDATE: signed on 20 March.", status="resolved", outcome="yes",           # a note added after
                                        resolved_at="2026-03-20T00:00:00+00:00", updated_at="2026-03-21T00:00:00+00:00")])
    ms.append_snapshots([Snapshot(market_id="m1", at="2026-03-10T06:00:00+00:00", p=0.4)])


def ev(i: str, pub: str, acq: str = "", body: str = "talks stalled over monitors") -> Evidence:
    return Evidence(id=i, kind="daily", source="t", title=i, body=body, publish_time=pub, event_time=pub, acquired_at=acq)


class Corpus:
    rows = [{"id": "d1", "kind": "daily", "type": "document", "title": "talks", "date": "2026-03-01", "snippet": "talks stalled", "score": 3.0}]

    def search(self, text, *, kinds=None, since="", until="", limit=20):
        return [dict(r) for r in self.rows]

    def entity(self, ref):
        return None


def run_it(q, docs):
    b = branches.ensure("p0b", controls.freeze_production_research())
    calls = {"n": 0}

    def planner(t, r):
        calls["n"] += 1
        return SimpleNamespace(queries=[rs.Query(market="M1", tool="search", arg="ceasefire")] if calls["n"] == 1 else []), 0.0

    (rec,) = runner.run_controlled(q, [b], sources.ListSource(docs), lambda p: (lambda t, r: (SimpleNamespace(probability_pct=20, rationale="r", cited=["d1"]), 0.01)),
                                   plan_ask_for=lambda pv: planner, corpus=Corpus())
    return rec


def test_question_text_is_read_as_of_the_cutoff_not_from_the_latest_revision():
    q = sources.question_from_market("m1", CUTOFF)
    assert q.rules == "Resolves YES if signed." and "UPDATE" not in q.rules and q.reference["market_rev"]["proven_pre_cutoff"] is True
    assert q.id.startswith("market-m1-2026-03-10-r")                                   # a corrected text is a new question id; the old one is never rewritten
    leaky = q.model_copy(update={"id": "old", "rules": ms.markets()["m1"].description})  # what the old code stored: the LAST revision
    runner.save_question(leaky)
    rec = run_it(leaky, [ev("d1", "2026-03-01", "2026-03-01")])
    rep = audit.audit_run(rec.run_id)
    assert not rep["clean"] and any(c["item"] == "question text" and c["verdict"] == "LEAK" for c in rep["context"])
    runner.save_question(q)
    good = run_it(q, [ev("d1", "2026-03-01", "2026-03-01")])
    assert audit.audit_run(good.run_id)["clean"]


def test_audit_lists_every_item_with_times_and_marks_what_it_cannot_prove():
    q = sources.question_from_market("m1", CUTOFF)
    runner.save_question(q)
    rec = run_it(q, [ev("d1", "2026-03-01"), ev("d-future", "2026-03-20", "2026-03-20")])       # d1: acquisition unknown; d-future never visible
    rep = audit.audit_run(rec.run_id)
    (d1,) = rep["evidence"]
    assert d1["id"] == "d1" and d1["publish_time"] == "2026-03-01" and d1["verdict"] == "unproven" and "acquisition time unknown" in d1["why"][0]
    chain = rep["features"][0]
    assert chain["verdict"] == "ok" and "identical" in chain["why"][0]                          # derived after the cutoff, but recomputation over visible docs matches
    price = next(c for c in rep["context"] if c["item"] == "market reference price")
    assert price["p"] == 0.4 and price["verdict"] == "ok" and rep["clean"] and rep["n_unproven"] >= 1


def test_audit_catches_a_shown_body_that_differs_from_the_snapshot():
    q = sources.question_from_market("m1", CUTOFF)
    runner.save_question(q)
    rec = run_it(q, [ev("d1", "2026-03-01", "2026-03-01")])
    man = store.read_json(f"runs/{rec.run_id}/manifest.json")
    man["shown"][0]["content_hash"] = "tampered"
    store.path(f"runs/{rec.run_id}/manifest.json").write_text(json.dumps(man), encoding="utf-8")
    rep = audit.audit_run(rec.run_id)
    assert not rep["clean"] and "differs from the snapshot body" in rep["evidence"][0]["why"][-1]


def test_a_claim_without_a_source_document_acquired_after_the_cutoff_is_hidden():
    db = sqlite3.connect(":memory:")
    db.executescript("CREATE TABLE claims (id TEXT, origin TEXT); CREATE TABLE events (id TEXT, origin TEXT); CREATE TABLE ingest_state (unit TEXT, fingerprint TEXT);"
                     "INSERT INTO claims VALUES ('c-late','u-late'),('c-unknown','u-unknown'); INSERT INTO ingest_state VALUES ('u-late','fp1'),('u-unknown','fp2');")
    c = SimpleNamespace(db=db, search=lambda text, **kw: [{"id": "c-late", "type": "claim", "date": "2026-03-02"}, {"id": "c-unknown", "type": "claim", "date": "2026-03-02"}])
    ledger = {("u-late", "fp1"): {"first_seen": "2026-04-01T00:00:00+00:00", "backfill": False}}
    view = cutoff_corpus.CutoffCorpus(c, set(), CUTOFF, ledger=ledger)
    assert [r["id"] for r in view.search("x")] == ["c-unknown"]                                 # dated before the cutoff, first held after it: gone
    assert view.dropped["ungrounded-derived-row-acquired-after-cutoff"] == 1 and sum(view.unproven.values()) == 1      # the other is kept, and counted as unproven
