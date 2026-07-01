"""Tests for the treatment_reviewer agent (planning gauntlet critique stage)."""

from __future__ import annotations

from algent_backend.agent_system.agents.editorial import review_loop
from algent_backend.agent_system.agents.editorial.review_contracts import (
    TreatmentFinding,
    TreatmentReview,
)
from algent_backend.agent_system.agents.editorial.review_messages import (
    build_treatment_review_message,
)
from algent_backend.agent_system.agents.editorial.treatment import (
    EditorialTreatment,
    FrameOption,
    TreatmentConcept,
)
from algent_backend.agent_system.agents.research.profile import (
    Claim,
    SignalProfile,
    SourceArtifact,
)
from algent_backend.agent_system.foundation.models import ModelSpec
from algent_backend.agent_system.runs.context import AgentRunContext


class _Structured:
    def __init__(self, obj):
        self._obj = obj

    def invoke(self, _messages, config=None):
        return self._obj


class _Model:
    def __init__(self, obj):
        self._obj = obj

    def with_structured_output(self, _schema):
        return _Structured(self._obj)


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


def _spec():
    return ModelSpec(provider="openai", model="gpt-5.4-mini")


def _profile() -> SignalProfile:
    return SignalProfile(
        id="prof_x", title="Fed path",
        source_ledger=[SourceArtifact(id="s1", url="https://fed.gov/x", source_type="primary")],
        claim_ledger=[Claim(id="c1", text="The Fed held rates", status="confirmed",
                            salience="high", grounding="snapshotted", supported_by=["s1"])],
    )


def _treatment() -> EditorialTreatment:
    return EditorialTreatment(
        id="trt_abc", profile_id="prof_x", title="Fed path", revision=1,
        chosen_frame=FrameOption(frame="two real risks pulling opposite ways"),
        concepts=[TreatmentConcept(id="k1", name="dual mandate tension", grounds_in=["c1"])],
    )


def test_reviewer_graph_produces_review_and_persists() -> None:
    review = TreatmentReview(
        id="model-set", verdict="needs_revision", summary="frame is close but a branch is missing",
        better_frame="center the split, not the odds",
        findings=[TreatmentFinding(id="", type="missing_branch", severity="high", target="k1",
                                   explanation="omits the dissent perspective", promotion_blocker=True)],
    )
    events: list = []
    graph = review_loop.build_treatment_reviewer_graph(_ctx(_Model(review), events), model_spec=_spec())

    out = graph.invoke({"treatment": _treatment().model_dump(), "profile": _profile().model_dump()})
    rev = TreatmentReview.model_validate(out["treatment_review"])

    assert rev.id == "treatment_review_trt_abc" and rev.treatment_id == "trt_abc"
    assert rev.profile_id == "prof_x" and rev.reviewer == "treatment_reviewer@v1" and rev.generated_at
    assert rev.findings[0].id == "tf_01"           # finding id assigned
    assert rev.verdict == "needs_revision"
    done = next(p for et, p in events if et == "treatment_review.completed")
    assert done["blockers"] == 1 and done["findings"] == 1


def test_reviewer_missing_inputs_is_unsound() -> None:
    graph = review_loop.build_treatment_reviewer_graph(_ctx(_Model(TreatmentReview(id="x")), []), model_spec=_spec())
    assert graph.invoke({"treatment": _treatment().model_dump()})["treatment_review"]["verdict"] == "unsound"
    assert graph.invoke({"profile": _profile().model_dump()})["treatment_review"]["verdict"] == "unsound"


def test_review_message_carries_treatment_and_profile() -> None:
    msg = build_treatment_review_message(_treatment(), _profile())
    assert "two real risks pulling opposite ways" in msg          # the treatment's frame
    assert "dual mandate tension" in msg                          # a concept
    assert "judge the treatment against THIS evidence" in msg
    assert "The Fed held rates" in msg and "c1 (high/snapshotted)" in msg  # the profile + id index


def test_treatment_reviewer_registered() -> None:
    from algent_backend.agent_system.agents.registry import default_agent_registry

    spec = default_agent_registry().get("treatment_reviewer")
    assert spec.tool_ids == () and spec.test_fixture is None  # tool-free; exercised via the gauntlet
