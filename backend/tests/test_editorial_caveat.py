"""Tests for the caveat_reviewer (v3b) — verify the prose keeps its flagged promises."""

from __future__ import annotations

from algent_backend.agent_system.agents.editorial import caveat_loop
from algent_backend.agent_system.agents.editorial.caveat_contracts import CaveatCheck, CaveatFinding
from algent_backend.agent_system.agents.editorial.caveat_messages import (
    caveat_worklists,
    has_promises_to_check,
)
from algent_backend.agent_system.agents.editorial.draft import ArticleDraft
from algent_backend.agent_system.agents.research.profile import (
    Claim,
    SignalProfile,
    SourceArtifact,
    SourceSnapshot,
)
from algent_backend.agent_system.foundation.models import ModelSpec
from algent_backend.agent_system.runs.context import AgentRunContext


class _Structured:
    def __init__(self, obj):
        self._o = obj

    def invoke(self, _m, config=None):
        return self._o


class _Model:
    def __init__(self, obj):
        self._o = obj
        self.calls = 0

    def with_structured_output(self, _s):
        return _Structured(self._o)


class _Resolver:
    def __init__(self, m):
        self._m = m

    def resolve(self, _s):
        return type("R", (), {"client": self._m})()


def _ctx(model, events):
    return AgentRunContext(
        run_id="t", model_resolver=_Resolver(model),  # type: ignore[arg-type]
        emit=lambda et, p=None: events.append((et, p or {})),
    )


def _spec():
    return ModelSpec(provider="openai", model="gpt-5.6-luna")


def _clean_profile() -> SignalProfile:
    return SignalProfile(id="p", title="t",
        source_ledger=[SourceArtifact(id="s1", url="u", snapshot=SourceSnapshot(content_hash="h"))],
        claim_ledger=[Claim(id="c1", text="core PCE rose 3.4%", status="confirmed",
                            grounding="snapshotted", supported_by=["s1"])])


def _clean_draft() -> ArticleDraft:
    return ArticleDraft(id="d", body="Inflation, with core PCE rose 3.4%, stayed high.",
                        cited_claim_ids=["c1"], cited_source_ids=["s1"])


def test_worklists_empty_when_confirmed_grounded_and_figures_match() -> None:
    work = caveat_worklists(_clean_draft(), _clean_profile())
    assert not has_promises_to_check(work)   # nothing to hedge -> the lane will short-circuit


def test_reviewer_short_circuits_free_when_nothing_flagged() -> None:
    # The mock would return needs_hedging IF called; a verified result proves no model call.
    events: list = []
    model = _Model(CaveatCheck(id="x", verdict="needs_hedging"))
    graph = caveat_loop.build_caveat_reviewer_graph(_ctx(model, events), model_spec=_spec())
    out = graph.invoke({"draft": _clean_draft().model_dump(), "profile": _clean_profile().model_dump()})
    assert out["caveat_check"]["verdict"] == "verified"           # short-circuit, not the mock
    assert any(et == "caveat_check.skipped" for et, _ in events)


def test_reviewer_runs_and_reports_needs_hedging_when_a_claim_is_flagged() -> None:
    prof = _clean_profile()
    prof.claim_ledger.append(Claim(id="c2", text="regulators are investigating whether X misled",
                                   status="contested", grounding="snapshotted", supported_by=["s1"]))
    draft = _clean_draft()
    draft.cited_claim_ids = ["c1", "c2"]
    draft.body = "Core PCE rose 3.4%. X misled clients."   # overstates the contested claim

    check = CaveatCheck(id="", verdict="needs_hedging", findings=[
        CaveatFinding(id="", target="c2", kind="overstatement",
                      issue="states an investigation's subject as settled fact", fix="attribute + hedge")])
    events: list = []
    graph = caveat_loop.build_caveat_reviewer_graph(_ctx(_Model(check), events), model_spec=_spec())
    out = graph.invoke({"draft": draft.model_dump(), "profile": prof.model_dump()})

    c = CaveatCheck.model_validate(out["caveat_check"])
    assert c.verdict == "needs_hedging" and c.draft_id == "d"
    assert c.findings[0].id == "cav_01" and c.reviewer == "caveat_reviewer@v1"
    assert any(et == "caveat_check.completed" for et, _ in events)


def test_caveat_reviewer_registered_on_nano() -> None:
    from algent_backend.agent_system.agents.registry import default_agent_registry

    spec = default_agent_registry().get("caveat_reviewer")
    assert spec.tool_ids == () and spec.default_model.provider == "meta" and spec.default_model.model == "muse-spark-1.2-contributor"
