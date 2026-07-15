"""Tests for the article_drafter (treatment + profile -> ArticleDraft, + enriched profile)."""

from __future__ import annotations

from algent_backend.agent_system.agents.editorial import draft_loop
from algent_backend.agent_system.agents.editorial.draft import ArticleDraft, DraftPayload
from algent_backend.agent_system.agents.editorial.draft_store import JsonDraftStore, render_draft
from algent_backend.agent_system.agents.editorial.treatment import EditorialTreatment, FrameOption
from algent_backend.agent_system.agents.research.assembly import finalize_profile
from algent_backend.agent_system.agents.research.profile import (
    Claim,
    ProfileAdditions,
    SignalProfile,
    SourceArtifact,
)
from algent_backend.agent_system.foundation.models import ModelSpec
from algent_backend.agent_system.runs.context import AgentRunContext


class _Resolver:
    def resolve(self, _spec):
        return type("R", (), {"client": object()})()


def _ctx(events):
    return AgentRunContext(
        run_id="t", model_resolver=_Resolver(),  # type: ignore[arg-type]
        tools={"web_search": object()}, emit=lambda et, p=None: events.append((et, p or {})),
    )


def _graph(context, monkeypatch, produced):
    monkeypatch.setattr(draft_loop, "build_react_loop", lambda *a, **k: object())
    monkeypatch.setattr(draft_loop, "stream_react_loop", lambda *a, **k: produced)
    return draft_loop.build_draft_graph(
        context, model_spec=ModelSpec(provider="openai", model="gpt-5.4-mini"),
        tool_ids=("web_search",), system_prompt="sys", search_channels=("keyword", "read"),
        paid_budget=2, cost_cap_usd=1.0,
    )


def _profile() -> SignalProfile:
    return finalize_profile(
        SignalProfile(
            id="", title="Fed path",
            source_ledger=[SourceArtifact(id="s1", url="https://fed.gov/x", source_type="primary")],
            claim_ledger=[Claim(id="c1", text="The Fed held rates", salience="high", supported_by=["s1"])],
        ),
        {"id": "vec_x"}, {}, model="m", generator="signal_profile@v2", stage="signal_profile",
    )


def _treatment(profile: SignalProfile) -> EditorialTreatment:
    return EditorialTreatment(
        id="trt_abc", profile_id=profile.id, title="Fed path",
        chosen_frame=FrameOption(frame="two real risks pulling opposite ways"),
    )


def test_drafter_produces_draft_validates_citations_and_persists(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("ALGENT_DRAFT_STORE", str(tmp_path))
    profile = _profile()
    real_claim, real_source = profile.claim_ledger[0].id, profile.source_ledger[0].id
    payload = DraftPayload(
        title="", standfirst="The Fed held, and the split is real.",
        body="The committee held rates. " * 8,
        cited_claim_ids=[real_claim, "c_ghost"],       # ghost must be dropped
        cited_source_ids=[real_source, "s_ghost"],
        research_note="pulled the exact PCE print",
    )
    events: list = []
    out = _graph(_ctx(events), monkeypatch, payload).invoke(
        {"treatment": _treatment(profile).model_dump(), "profile": profile.model_dump()})

    draft = ArticleDraft.model_validate(out["draft"])
    assert draft.id == draft_loop._draft_id("trt_abc") and draft.treatment_id == "trt_abc"
    assert draft.profile_id == profile.id and draft.title == "Fed path"  # filled from treatment
    assert draft.frame == "two real risks pulling opposite ways"
    assert draft.cited_claim_ids == [real_claim] and draft.cited_source_ids == [real_source]  # ghosts dropped
    assert draft.word_count > 0 and draft.generator == "article_drafter@v1" and draft.generated_at
    assert out["profile"]["revision"] == 1  # no additions -> profile unchanged

    store = JsonDraftStore(tmp_path)
    assert store.get(draft.id) is not None
    assert [d.id for d in store.list_for_treatment("trt_abc")] == [draft.id]


def test_drafter_enriches_profile_when_it_finds_new_evidence(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("ALGENT_DRAFT_STORE", str(tmp_path))
    monkeypatch.setenv("ALGENT_PROFILE_STORE", str(tmp_path))
    profile = _profile()
    payload = DraftPayload(
        body="Prose citing the new detail.",
        additions=ProfileAdditions(
            sources=[SourceArtifact(id="ns1", url="https://reuters.com/pce", source_type="secondary")],
            claims=[Claim(id="nc1", text="core PCE printed 3.4% in May", supported_by=["ns1"])],
        ),
    )
    events: list = []
    out = _graph(_ctx(events), monkeypatch, payload).invoke(
        {"treatment": _treatment(profile).model_dump(), "profile": profile.model_dump()})

    # Enrich-back: profile bumped, drafting-stage provenance on the new claim.
    assert out["profile"]["revision"] == 2
    added = next(c for c in out["profile"]["claim_ledger"] if "core PCE" in c["text"])
    assert added["provenance"]["added_by_stage"] == "drafting"
    done = next(p for et, p in events if et == "draft.completed")
    assert done["added_claims"] == 1 and done["profile_revision"] == 2
    assert "estimated_usd" in done   # drafting surfaces its spend (the rail sums it)


def test_drafter_missing_input_is_empty_draft(monkeypatch) -> None:
    events: list = []
    graph = _graph(_ctx(events), monkeypatch, DraftPayload())  # patches the react loop at build time
    out = graph.invoke({"treatment": _treatment(_profile()).model_dump()})  # profile missing
    assert out["draft"]["id"] == "draft_none"
    assert any(et == "draft.no_input" for et, _ in events)


def test_render_draft_shows_piece_and_footer() -> None:
    md = render_draft(ArticleDraft(
        id="drf_x", treatment_id="trt_abc", profile_id="prof_x", frame="the split",
        title="A real split", standfirst="dek here", body="Body paragraph.", word_count=2,
        cited_claim_ids=["clm_1"], research_note="found the print",
    ))
    assert "A real split" in md and "dek here" in md and "Body paragraph." in md
    assert "frame: the split" in md and "found the print" in md and "clm_1" in md


def test_article_drafter_registered_with_fixture() -> None:
    from pathlib import Path

    from algent_backend.agent_system.agents.registry import default_agent_registry

    spec = default_agent_registry().get("article_drafter")
    assert spec.tool_ids == ("web_search",)  # a researching stage
    assert spec.test_fixture is not None and spec.test_fixture.input_key is None  # whole-state fixture
    assert Path(spec.test_fixture.input_file).exists()
