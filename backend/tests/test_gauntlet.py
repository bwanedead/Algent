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
    # Attempted, not "addressed": review ids are renumbered per review, so resolution cannot be
    # read off an id diff. What is honestly countable is what was sent out and what remains.
    assert set(g["findings_attempted"]) == {"f1", "f2"}
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



def test_ids_that_change_case_do_not_fake_resolution(monkeypatch) -> None:
    """The live contradiction: 10 findings "addressed", 10 still open.

    The first review numbered them f01..f10 and the re-review F01..F10. An id diff read that as
    every finding resolved. Remaining is the count that tells the truth.
    """
    base = SignalProfile(id="p", title="t", revision=1).model_dump()
    first = ReviewReport(id="r1", verdict="needs_enrichment", findings=[
        ReviewFinding(id="f01", type="missing_scope", lane="primary_source",
                      explanation="No independent peer commentary beyond one taxonomist."),
    ]).model_dump()
    again = ReviewReport(id="r2", verdict="needs_enrichment", findings=[
        ReviewFinding(id="F01", type="missing_scope", lane="primary_source", maturity_blocker=True,
                      explanation="No independent peer commentary beyond one taxonomist."),
    ]).model_dump()
    calls = {"n": 0}

    def fake_reviewer(_c):
        r = first if calls["n"] == 0 else again
        calls["n"] += 1
        return _FakeGraph({"review": r})

    monkeypatch.setattr(orchestrator, "build_reviewer", fake_reviewer)
    monkeypatch.setattr(primary_source, "build_graph",
                        lambda c: _FakeGraph({"profile": {**base, "revision": 2}}))
    monkeypatch.setattr(counter_perspective, "build_graph",
                        lambda c: _FakeGraph({"profile": {**base, "revision": 2}}))

    out = orchestrator.build_gauntlet_graph(_ctx([])).invoke({"profile": base})
    assert out["gauntlet"]["remaining_findings"] == 1

    # And the gap is not thrown away: it reaches the planner as disclosed uncertainty.
    questions = out["profile"]["open_questions"]
    assert any("No independent peer commentary" in q and "blocking" in q for q in questions)


def test_disclosure_never_duplicates_an_open_question() -> None:
    profile = {"open_questions": ["[unresolved] Only one source."]}
    out = orchestrator._disclose_unresolved(
        profile, [{"explanation": "Only one source."}, {"explanation": "  "}])
    assert out["open_questions"] == ["[unresolved] Only one source."]


def test_a_lane_does_not_pay_research_prices_to_confirm_nothing_is_wrong() -> None:
    """Enrichment costs ~5 paid searches per finding. It was spending them on `low` findings
    whose own text said the profile was fine. Only blockers and medium-or-worse are chased."""
    from algent_backend.agent_system.agents.enrich.base import _select_findings
    from algent_backend.agent_system.agents.review.contracts import ReviewFinding, ReviewReport

    def f(fid: str, severity: str, blocker: bool = False) -> ReviewFinding:
        return ReviewFinding(id=fid, type="thin_grounding", lane="primary_source",
                             severity=severity, maturity_blocker=blocker, target="c1",
                             explanation="x")

    report = ReviewReport(id="rv", findings=[f("a", "low"), f("b", "high"), f("c", "low")])
    assert [x.id for x in _select_findings(report, "primary_source")] == ["b"]

    # A lane with nothing worth chasing does not run at all.
    assert _select_findings(ReviewReport(id="rv", findings=[f("a", "low")]), "primary_source") == []
    # ...unless a low finding is flagged as blocking maturity, which is a real assignment.
    assert [x.id for x in _select_findings(
        ReviewReport(id="rv", findings=[f("a", "low", blocker=True)]), "primary_source")] == ["a"]
