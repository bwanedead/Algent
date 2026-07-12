"""Tests for the editorial_pipeline orchestrator (profile -> article)."""

from __future__ import annotations

from algent_backend.agent_system.agents.editorial import pipeline as pl
from algent_backend.agent_system.runs.context import AgentRunContext


class _Graph:
    def __init__(self, out):
        self._out = out

    def invoke(self, _state, _config=None):
        return self._out


def _ctx(events):
    return AgentRunContext(
        run_id="t", model_resolver=object(),  # type: ignore[arg-type]
        emit=lambda et, p=None: events.append((et, p or {})),
    )


def _wire(monkeypatch, plan_out, draft_out, caveat_out, headline_out=None):
    monkeypatch.setattr(pl, "build_planning_gauntlet_graph", lambda ctx: _Graph(plan_out))
    monkeypatch.setattr(pl, "build_drafting_gauntlet_graph", lambda ctx: _Graph(draft_out))
    monkeypatch.setattr(pl, "build_headline_writer", lambda ctx: _Graph(headline_out or {"headline": {}}))
    monkeypatch.setattr(pl, "build_caveat_reviewer", lambda ctx: _Graph(caveat_out))


def test_caveated_piece_becomes_publishable_once_caveats_verified(monkeypatch) -> None:
    plan_out = {"treatment": {"id": "trt_x"}, "gauntlet": {"final_verdict": "needs_revision"}}
    draft_out = {
        "draft": {"id": "drf_x", "title": "A real Fed piece", "word_count": 420},
        "gauntlet": {"outcome": "grounded_with_caveats", "promoted": True, "barriers": ["src_a"]},
    }
    _wire(monkeypatch, plan_out, draft_out, {"caveat_check": {"verdict": "verified", "findings": []}})

    events: list = []
    out = pl.build_editorial_pipeline_graph(_ctx(events)).invoke({"profile": {"id": "prof_x"}})

    r = out["pipeline"]
    assert r["treatment_id"] == "trt_x" and r["draft_id"] == "drf_x"
    assert r["draft_outcome"] == "grounded_with_caveats"
    # v3b verified the caveats are actually in the prose -> the pending promise is now cleared.
    assert r["status"] == "publishable" and r["publishable"] is True
    assert r["caveat_verdict"] == "verified" and r["barriers"] == ["src_a"]
    assert any(et == "editorial_pipeline.completed" for et, _ in events)


def test_pipeline_applies_the_truthful_headline(monkeypatch) -> None:
    plan_out = {"treatment": {"id": "trt_x"}, "gauntlet": {}}
    draft_out = {"draft": {"id": "drf_x", "title": "working title", "word_count": 400},
                 "gauntlet": {"outcome": "grounded", "promoted": True}}
    headline_out = {"headline": {"title": "Fed holds, hike tail still live", "standfirst": "the nuance"}}
    _wire(monkeypatch, plan_out, draft_out, {"caveat_check": {"verdict": "verified"}}, headline_out)

    r = pl.build_editorial_pipeline_graph(_ctx([])).invoke({"profile": {"id": "prof_x"}})["pipeline"]
    assert r["article_title"] == "Fed holds, hike tail still live"   # retitled from the working title
    assert r["status"] == "publishable"


def test_unhedged_prose_holds_the_piece(monkeypatch) -> None:
    plan_out = {"treatment": {"id": "trt_x"}, "gauntlet": {}}
    draft_out = {"draft": {"id": "drf_x"}, "gauntlet": {"outcome": "grounded_with_caveats", "barriers": ["s"]}}
    caveat_out = {"caveat_check": {"verdict": "needs_hedging", "findings": [{"id": "cav_01"}]}}
    _wire(monkeypatch, plan_out, draft_out, caveat_out)

    r = pl.build_editorial_pipeline_graph(_ctx([])).invoke({"profile": {"id": "prof_x"}})["pipeline"]
    assert r["status"] == "needs_hedging" and r["publishable"] is False
    assert r["caveat_verdict"] == "needs_hedging" and r["caveat_findings"] == 1


def test_pipeline_no_profile_is_not_publishable(monkeypatch) -> None:
    out = pl.build_editorial_pipeline_graph(_ctx([])).invoke({})
    assert out["pipeline"]["publishable"] is False


def test_editorial_pipeline_registered_with_fixture() -> None:
    from pathlib import Path

    from algent_backend.agent_system.agents.registry import default_agent_registry

    spec = default_agent_registry().get("editorial_pipeline")
    assert spec.test_fixture is not None and spec.test_fixture.input_key == "profile"
    assert Path(spec.test_fixture.input_file).exists()
