"""Experiment lab, phase 2: faithful P0, acquisition time, decision replay, the common question set, origin chains (stubbed models, temp stores)."""

from __future__ import annotations

from types import SimpleNamespace
from typing import Any

import pytest

from algent_backend.experiment import branches, controls, cutoff_corpus, policies, runner, sources, store
from algent_backend.experiment.contracts import Evidence, Question
from algent_backend.markets import research as rs

CUTOFF = "2026-03-10T12:00:00+00:00"


@pytest.fixture(autouse=True)
def stores(tmp_path, monkeypatch):
    monkeypatch.setenv("ALGENT_EXPERIMENT_STORE", str(tmp_path / "lab"))
    monkeypatch.setenv("ALGENT_MARKETS_STORE", str(tmp_path / "markets"))
    monkeypatch.setenv("ALGENT_ACQUISITION_STORE", str(tmp_path / "acq"))


def ev(i: str, pub: str, body: str = "", acq: str = "", title: str = "") -> Evidence:
    return Evidence(id=i, kind="daily", source="test", title=title or i, body=body, publish_time=pub, event_time=pub, acquired_at=acq or pub)


Q = Question(id="q1", text="Will Aldoria and Brevia sign a ceasefire by 2026-03-31?", rules="Resolves YES if signed.", cutoff=CUTOFF, closes_at="2026-03-31T00:00:00+00:00",
             source="market:m1", reference={"market_p": 0.4})


class FakeCorpus:
    """Answers every query with the SAME rows regardless of ``until``: the best match is the post-cutoff document, so only the cutoff view can hide it."""

    def __init__(self) -> None:
        self.rows = [
            {"id": "d-new", "kind": "daily", "type": "document", "title": "Ceasefire signed", "date": "2026-03-20", "snippet": "the ceasefire was signed on the 20th", "score": 9.0},
            {"id": "c-late", "kind": "claim", "type": "claim", "title": "", "date": "2026-03-12", "snippet": "ceasefire signed claim", "score": 8.0},
            {"id": "c-hidden", "kind": "claim", "type": "claim", "title": "", "date": "2026-03-01", "document_id": "d-new", "snippet": "claim from a hidden document", "score": 7.0},
            {"id": "d-old", "kind": "daily", "type": "document", "title": "Ceasefire talks stalled", "date": "2026-03-01", "snippet": "talks stalled", "score": 3.0},
            {"id": "ev-old", "kind": "development", "type": "event", "title": "Border monitors deployed", "date": "2026-03-05", "snippet": "", "score": 2.0},
        ]
        self.queries: list[str] = []

    def search(self, text: str, *, kinds=None, since="", until="", limit=20):
        self.queries.append(text)
        return [dict(r) for r in self.rows]

    def entity(self, ref: str):
        return None


def planner(spend: float = 0.01):
    calls = []

    def plan(task: str, role: str):
        calls.append(task)
        qs = [rs.Query(market="M1", tool="search", arg="ceasefire signed")] if len(calls) == 1 else []
        return SimpleNamespace(queries=qs), spend

    plan.calls = calls  # type: ignore[attr-defined]
    return plan


def stub(p: float):
    seen: list[str] = []

    def ask(task: str, role: str):
        seen.append(task)
        return SimpleNamespace(probability=p, rationale="because", cited=["d-old"]), 0.01

    ask.seen = seen  # type: ignore[attr-defined]
    return ask


DOCS = [ev("d-old", "2026-03-01", "Talks stalled"), ev("d-new", "2026-03-20", "Ceasefire signed"), ev("ev-old", "2026-03-05", "Monitors")]


# ── 1. faithful P0 ─────────────────────────────────────────────────────────────────────────────
def test_cutoff_corpus_hides_post_cutoff_rows_even_when_best_match():
    view = cutoff_corpus.CutoffCorpus(FakeCorpus(), {"d-old"}, CUTOFF)
    ids = [r["id"] for r in view.search("ceasefire")]
    assert ids == ["d-old", "ev-old"]                       # d-new (best match, after cutoff and not in the snapshot), c-late (derived after), c-hidden (hidden source) are gone
    assert view.dropped["document-not-in-snapshot"] == 1 and view.dropped["derived-after-cutoff-or-source-hidden"] == 2


def test_production_research_policy_runs_against_the_cutoff_view_only():
    p0 = policies.freeze_blind_forecaster()
    p0b = controls.freeze_production_research()
    assert p0b.id != p0.id and p0b.parent == p0.id and store.read_json("frozen/p0-research.json")["supersedes"] == p0.id
    assert controls.freeze_production_research().id == p0b.id and store.read_json("frozen/p0.json")["protocol_id"] == p0.id      # the old P0 stays as it is
    assert p0b.policies["evidence"].ref == "evidence/production-research@1" and p0b.policies["prompts"].digest == p0.policies["prompts"].digest
    corpus, plan, ask = FakeCorpus(), planner(), stub(0.3)
    b = branches.ensure("p0b", p0b)
    (rec,) = runner.run_controlled(Q, [b], sources.ListSource(DOCS), lambda proto: ask, plan_ask_for=lambda pv: plan, corpus=corpus)
    prompt = store.path(f"runs/{rec.run_id}/prompt.txt").read_text(encoding="utf-8")
    assert "[d-old]" in prompt and "[ev-old]" in prompt
    assert all(x not in prompt for x in ("d-new", "c-late", "c-hidden"))          # the post-cutoff best match is invisible to the model
    man = store.read_json(f"runs/{rec.run_id}/manifest.json")
    assert man["research"]["hidden_by_cutoff"] and sorted(man["research"]["shown"]) == ["d-old", "ev-old"] and not man["research"]["knob_drift"]
    assert sorted(s["id"] for s in man["shown"]) == ["d-old", "ev-old"]
    assert rec.usd == pytest.approx(0.02)                                           # the planner's spend is part of the protocol's cost
    assert not runner.verify(rec.run_id) and not controls.impl_drift(p0b)


def test_planned_policy_without_a_planner_is_refused():
    b = branches.ensure("p0b", controls.freeze_production_research())
    with pytest.raises(ValueError):
        runner.run_controlled(Q, [b], sources.ListSource(DOCS), lambda proto: stub(0.3), corpus=None)
