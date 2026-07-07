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


def test_pipeline_chains_planning_then_drafting_into_an_article(monkeypatch) -> None:
    plan_out = {"treatment": {"id": "trt_x"}, "gauntlet": {"final_verdict": "needs_revision"}}
    draft_out = {
        "draft": {"id": "drf_x", "title": "A real Fed piece", "word_count": 420},
        "gauntlet": {"outcome": "grounded_with_caveats", "promoted": True, "barriers": ["src_a"]},
    }
    monkeypatch.setattr(pl, "build_planning_gauntlet_graph", lambda ctx: _Graph(plan_out))
    monkeypatch.setattr(pl, "build_drafting_gauntlet_graph", lambda ctx: _Graph(draft_out))

    events: list = []
    out = pl.build_editorial_pipeline_graph(_ctx(events)).invoke({"profile": {"id": "prof_x"}})

    r = out["pipeline"]
    assert r["treatment_id"] == "trt_x" and r["draft_id"] == "drf_x"
    assert r["article_title"] == "A real Fed piece" and r["word_count"] == 420
    assert r["draft_outcome"] == "grounded_with_caveats" and r["publishable"] is True
    assert r["status"] == "publishable_pending_caveat_check"   # honest: the caveat isn't verified yet
    assert r["barriers"] == ["src_a"] and r["treatment_verdict"] == "needs_revision"
    assert any(et == "editorial_pipeline.completed" for et, _ in events)


def test_pipeline_no_profile_is_not_publishable(monkeypatch) -> None:
    out = pl.build_editorial_pipeline_graph(_ctx([])).invoke({})
    assert out["pipeline"]["publishable"] is False


def test_editorial_pipeline_registered_with_fixture() -> None:
    from pathlib import Path

    from algent_backend.agent_system.agents.registry import default_agent_registry

    spec = default_agent_registry().get("editorial_pipeline")
    assert spec.test_fixture is not None and spec.test_fixture.input_key == "profile"
    assert Path(spec.test_fixture.input_file).exists()
