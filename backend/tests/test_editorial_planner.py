"""Tests for the editorial_planner agent (planning stage: profile -> EditorialTreatment)."""

from __future__ import annotations

from algent_backend.agent_system.agents.editorial import loop as plan_loop
from algent_backend.agent_system.agents.editorial.briefing import render_treatment
from algent_backend.agent_system.agents.editorial.messages import build_treatment_message
from algent_backend.agent_system.agents.editorial.treatment import (
    EditorialTreatment,
    FrameOption,
    PerspectiveTake,
    TreatmentConcept,
)
from algent_backend.agent_system.agents.research.profile import (
    Claim,
    SignalProfile,
    SourceArtifact,
    Thread,
)
from algent_backend.agent_system.foundation.models import ModelSpec
from algent_backend.agent_system.runs.context import AgentRunContext


class _Structured:
    def __init__(self, treatment):
        self._t = treatment

    def invoke(self, _messages, config=None):
        return self._t


class _Model:
    def __init__(self, treatment):
        self._t = treatment

    def with_structured_output(self, _schema):
        return _Structured(self._t)


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
        id="prof_x", title="Fed path", profile_status="needs_verification",
        source_ledger=[SourceArtifact(id="s1", url="https://fed.gov/x", publisher="Fed", source_type="primary")],
        claim_ledger=[Claim(id="c1", text="The Fed held rates", status="confirmed",
                            salience="high", grounding="snapshotted", supported_by=["s1"])],
        threads=[Thread(id="t1", title="The split committee", body="...", salience="high")],
    )


def _treatment() -> EditorialTreatment:
    # Note the dangling references the harness must drop: depends_on k_missing,
    # grounds_in c_ghost, must_use s_ghost, reader_path k_missing.
    return EditorialTreatment(
        id="model-set", title="",
        chosen_frame=FrameOption(frame="two real risks pulling opposite ways", rationale="reveals the split"),
        rejected_frames=[FrameOption(frame="the Fed is behind the curve", rationale="smuggles a verdict")],
        core_understanding="The hold reflects a genuine split, not indecision.",
        concepts=[
            TreatmentConcept(id="k1", name="dual mandate tension",
                             depends_on=["k_missing"], grounds_in=["c1", "c_ghost"]),
            TreatmentConcept(id="", name="market reaction", depends_on=["k1"], grounds_in=["t1"]),
        ],
        reader_path=["k1", "k_missing", "k02"],
        perspectives=[PerspectiveTake(id="", label="doves", steelman="cut now", grounds_in=["c1", "c_ghost"])],
        deception_risks=["framing the hold as weakness"],
        must_use_items=["c1", "s_ghost"],
    )


def test_planner_graph_produces_treatment_validates_refs_and_persists(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("ALGENT_TREATMENT_STORE", str(tmp_path))  # durable save -> tmp, not the repo
    events: list = []
    graph = plan_loop.build_planning_graph(_ctx(_Model(_treatment()), events), model_spec=_spec())

    out = graph.invoke({"profile": _profile().model_dump()})
    t = EditorialTreatment.model_validate(out["treatment"])

    # Harness identity stamping — content-addressed by (profile, frame), revision 1.
    assert t.id == plan_loop._treatment_id("prof_x", "two real risks pulling opposite ways")
    assert t.id.startswith("trt_") and t.profile_id == "prof_x" and t.revision == 1
    assert t.title == "Fed path"  # filled from the profile when the model left it blank
    assert t.generator == "editorial_planner@v1" and t.generated_at

    # Persisted to the durable store and recoverable by profile lineage.
    from algent_backend.agent_system.agents.editorial.store import JsonTreatmentStore
    store = JsonTreatmentStore(tmp_path)
    assert store.get(t.id) is not None
    assert [k.id for k in store.list_for_profile("prof_x")] == [t.id]

    # Blank ids assigned; model ids kept.
    ids = [c.id for c in t.concepts]
    assert ids[0] == "k1" and ids[1] == "k02"
    assert t.perspectives[0].id == "p01"

    # Dangling references dropped; valid ones kept.
    assert t.concepts[0].depends_on == []                 # k_missing dropped
    assert t.concepts[0].grounds_in == ["c1"]             # c_ghost dropped
    assert t.concepts[1].depends_on == ["k1"]             # real concept dep kept
    assert t.reader_path == ["k1", "k02"]                 # k_missing dropped
    assert t.perspectives[0].grounds_in == ["c1"]         # c_ghost dropped
    assert t.must_use_items == ["c1"]                     # s_ghost dropped

    done = next(p for et, p in events if et == "treatment.completed")
    assert done["concepts"] == 2 and done["deception_risks"] == 1


def test_planner_no_profile_is_empty_treatment() -> None:
    graph = plan_loop.build_planning_graph(_ctx(_Model(_treatment()), []), model_spec=_spec())
    out = graph.invoke({})
    assert out["treatment"]["id"] == "treatment_none"


def test_treatment_message_carries_id_index_and_briefing() -> None:
    msg = build_treatment_message(_profile())
    assert "Addressable item ids" in msg
    assert "c1 (high/snapshotted)" in msg and "t1" in msg and "s1 (primary)" in msg
    assert "Briefing" in msg and "The Fed held rates" in msg
    assert "Do NOT write prose" in msg


def test_render_treatment_shows_frame_and_molecule() -> None:
    md = render_treatment(plan_loop._finalize(_treatment(), _profile(), "m"))
    assert "two real risks pulling opposite ways" in md   # chosen frame
    assert "~~the Fed is behind the curve~~" in md         # rejected frame
    assert "dual mandate tension" in md and "`k1`" in md   # a concept node
    assert "Deception risks" in md


def test_editorial_planner_registered_with_fixture() -> None:
    from pathlib import Path

    from algent_backend.agent_system.agents.registry import default_agent_registry

    spec = default_agent_registry().get("editorial_planner")
    assert spec.tool_ids == ()  # tool-free judgment
    assert spec.test_fixture is not None and spec.test_fixture.input_key == "profile"
    assert Path(spec.test_fixture.input_file).exists()
