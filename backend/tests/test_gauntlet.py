"""Tests for the gauntlet orchestrator (v1: review -> enrich -> merge -> re-review)."""

from __future__ import annotations

from algent_backend.agent_system.agents.enrich import counter_perspective, primary_source
from algent_backend.agent_system.agents.gauntlet import orchestrator
from algent_backend.agent_system.agents.research.profile import SignalProfile
from algent_backend.agent_system.agents.review.contracts import ReviewFinding, ReviewReport
from algent_backend.agent_system.runs.context import AgentRunContext


class _FakeGraph:
    def __init__(self, result):
        self._r = result

    def invoke(self, _state, config=None):
        return self._r


def _ctx(events):
    return AgentRunContext(run_id="t", model_resolver=object(),  # type: ignore[arg-type]
                           emit=lambda et, p=None: events.append((et, p or {})))


def test_gauntlet_reviews_enriches_sequentially_and_re_reviews(monkeypatch) -> None:
    base = SignalProfile(id="prof_x", title="Fed path", revision=1).model_dump()
    review = ReviewReport(id="r1", verdict="needs_enrichment", findings=[
        ReviewFinding(id="f1", type="missing_primary_source", lane="primary_source", maturity_blocker=True),
        ReviewFinding(id="f2", type="missing_perspective", lane="counter_perspective"),
    ]).model_dump()
    rereview = ReviewReport(id="r2", verdict="needs_verification",
                            findings=[ReviewFinding(id="f9", type="overclaim")]).model_dump()

    calls = {"n": 0}

    def fake_reviewer(_context):
        result = review if calls["n"] == 0 else rereview  # 1st = review, 2nd = re-review
        calls["n"] += 1
        return _FakeGraph({"review": result})

    monkeypatch.setattr(orchestrator, "build_reviewer", fake_reviewer)
    monkeypatch.setattr(primary_source, "build_graph",
                        lambda c: _FakeGraph({"profile": {**base, "revision": 2}, "addressed": ["f1"]}))
    monkeypatch.setattr(counter_perspective, "build_graph",
                        lambda c: _FakeGraph({"profile": {**base, "revision": 3}, "addressed": ["f2"]}))

    events: list = []
    out = orchestrator.build_gauntlet_graph(_ctx(events)).invoke({"profile": base})

    g = out["gauntlet"]
    assert g["initial_verdict"] == "needs_enrichment" and g["final_verdict"] == "needs_verification"
    assert g["lanes_run"] == ["primary_source", "counter_perspective"]  # deterministic order
    assert set(g["findings_addressed"]) == {"f1", "f2"}
    assert g["starting_revision"] == 1 and g["ending_revision"] == 3  # each lane bumped sequentially
    assert g["remaining_blockers"] == 0 and g["remaining_findings"] == 1
    assert any(et == "gauntlet.completed" for et, _ in events)


def test_gauntlet_skips_lanes_with_no_findings(monkeypatch) -> None:
    base = SignalProfile(id="p", title="t", revision=1).model_dump()
    review = ReviewReport(id="r", verdict="needs_enrichment",
                          findings=[ReviewFinding(id="f1", type="needs_data", lane="analytics")]).model_dump()
    calls = {"n": 0}

    def fake_reviewer(_context):
        calls["n"] += 1
        return _FakeGraph({"review": review})

    monkeypatch.setattr(orchestrator, "build_reviewer", fake_reviewer)
    # neither lane should be invoked (no matching findings) — if they were, this would error
    monkeypatch.setattr(primary_source, "build_graph", lambda c: (_ for _ in ()).throw(AssertionError("ran")))
    monkeypatch.setattr(counter_perspective, "build_graph", lambda c: (_ for _ in ()).throw(AssertionError("ran")))

    out = orchestrator.build_gauntlet_graph(_ctx([])).invoke({"profile": base})
    g = out["gauntlet"]
    assert g["lanes_run"] == []  # nothing to run
    assert calls["n"] == 1  # no re-review when profile unchanged and no enrichment
    assert g["final_verdict"] == g["initial_verdict"] == "needs_enrichment"


def test_profile_gauntlet_registered_with_fixture() -> None:
    from pathlib import Path

    from algent_backend.agent_system.agents.registry import default_agent_registry

    spec = default_agent_registry().get("profile_gauntlet")
    assert spec.tool_ids == ("web_search",)  # so enricher sub-graphs can reach the facade
    assert spec.test_fixture is not None and spec.test_fixture.input_key == "profile"
    assert Path(spec.test_fixture.input_file).exists()
