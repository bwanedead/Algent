"""Tests for the planning_gauntlet orchestrator (plan -> review -> revise -> re-review)."""

from __future__ import annotations

from algent_backend.agent_system.agents.editorial import gauntlet as pg
from algent_backend.agent_system.agents.editorial.review_contracts import (
    TreatmentFinding,
    TreatmentReview,
)
from algent_backend.agent_system.agents.editorial.treatment import (
    EditorialTreatment,
    FrameOption,
    TreatmentConcept,
)
from algent_backend.agent_system.agents.research.profile import Claim, SignalProfile
from algent_backend.agent_system.runs.context import AgentRunContext


class _Structured:
    def __init__(self, obj):
        self._obj = obj

    def invoke(self, _messages, config=None):
        return self._obj


class _Model:
    """One fake model that answers with a treatment or a review depending on the schema."""

    def __init__(self, treatment, review):
        self._t, self._r = treatment, review

    def with_structured_output(self, schema):
        return _Structured(self._t if schema is EditorialTreatment else self._r)


class _Resolver:
    def __init__(self, model):
        self._m = model

    def resolve(self, _spec):
        return type("R", (), {"client": self._m})()


def _ctx(model, events):
    return AgentRunContext(
        run_id="t", model_resolver=_Resolver(model),  # type: ignore[arg-type]
        emit=lambda et, p=None: events.append((et, p or {})),
    )


def _profile() -> SignalProfile:
    return SignalProfile(
        id="prof_x", title="Fed path",
        claim_ledger=[Claim(id="c1", text="The Fed held rates", salience="high", grounding="snapshotted")],
    )


def _treatment() -> EditorialTreatment:
    return EditorialTreatment(
        id="", title="", chosen_frame=FrameOption(frame="two real risks pulling opposite ways"),
        concepts=[TreatmentConcept(id="k1", name="dual mandate tension", grounds_in=["c1"])],
    )


def _review(verdict: str) -> TreatmentReview:
    return TreatmentReview(
        id="", verdict=verdict, summary="assessment",
        better_frame="center the split" if verdict != "promoted" else "",
        findings=[TreatmentFinding(id="", type="missing_branch", severity="high", target="k1",
                                   explanation="omits dissent", promotion_blocker=(verdict != "promoted"))],
    )


def test_gauntlet_revises_when_not_promoted(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("ALGENT_TREATMENT_STORE", str(tmp_path))
    events: list = []
    ctx = _ctx(_Model(_treatment(), _review("needs_revision")), events)
    out = pg.build_planning_gauntlet_graph(ctx).invoke({"profile": _profile().model_dump()})

    report = out["gauntlet"]
    assert report["revised"] is True and report["promoted"] is False
    assert report["ending_revision"] == 2                 # a revision pass ran (rev bumped)
    assert report["better_frame_offered"] == "center the split"
    # The matured (rev-2) treatment persisted under the SAME id (revision kept the node).
    from algent_backend.agent_system.agents.editorial.store import JsonTreatmentStore
    kin = JsonTreatmentStore(tmp_path).list_for_profile("prof_x")
    assert len(kin) == 1 and kin[0].revision == 2
    assert any(et == "planning_gauntlet.completed" for et, _ in events)


def test_gauntlet_stops_when_promoted(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("ALGENT_TREATMENT_STORE", str(tmp_path))
    ctx = _ctx(_Model(_treatment(), _review("promoted")), [])
    out = pg.build_planning_gauntlet_graph(ctx).invoke({"profile": _profile().model_dump()})

    report = out["gauntlet"]
    assert report["promoted"] is True and report["revised"] is False
    assert report["ending_revision"] == 1                 # promoted first pass — no revision
    assert report["final_verdict"] == "promoted"


def test_gauntlet_no_profile_is_unsound() -> None:
    out = pg.build_planning_gauntlet_graph(_ctx(_Model(_treatment(), _review("promoted")), [])).invoke({})
    assert out["gauntlet"]["final_verdict"] == "unsound"


def test_planning_gauntlet_registered_with_fixture() -> None:
    from pathlib import Path

    from algent_backend.agent_system.agents.registry import default_agent_registry

    spec = default_agent_registry().get("planning_gauntlet")
    assert spec.test_fixture is not None and spec.test_fixture.input_key == "profile"
    assert Path(spec.test_fixture.input_file).exists()
