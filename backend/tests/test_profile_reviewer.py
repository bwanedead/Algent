"""Tests for the profile_reviewer agent (gauntlet stage 1: profile -> ReviewReport)."""

from __future__ import annotations

from algent_backend.agent_system.agents.research.profile import (
    Claim,
    SignalProfile,
    SourceArtifact,
)
from algent_backend.agent_system.agents.review import loop as review_loop
from algent_backend.agent_system.agents.review.contracts import ReviewFinding, ReviewReport
from algent_backend.agent_system.agents.review.messages import build_review_message
from algent_backend.agent_system.foundation.models import ModelSpec
from algent_backend.agent_system.runs.context import AgentRunContext


class _Structured:
    def __init__(self, report):
        self._r = report

    def invoke(self, _messages, config=None):
        return self._r


class _Model:
    def __init__(self, report):
        self._r = report

    def with_structured_output(self, _schema):
        return _Structured(self._r)


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
        source_ledger=[SourceArtifact(id="s1", url="https://polymarket.com/x", publisher="Polymarket")],
        claim_ledger=[Claim(id="c1", text="Markets expect a hold", status="confirmed",
                            salience="high", grounding="snippet_only", supported_by=["s1"])],
    )


def test_reviewer_graph_produces_report_and_persists(monkeypatch) -> None:
    report = ReviewReport(
        id="model-set", verdict="needs_enrichment", summary="thin",
        findings=[ReviewFinding(id="", type="thin_grounding", severity="high", target="c1",
                                explanation="high-salience claim only snippet-sourced",
                                lane="primary_source", maturity_blocker=True)],
        recommended_lanes=["primary_source", "counter_perspective"],
    )
    events: list = []
    graph = review_loop.build_reviewer_graph(_ctx(_Model(report), events), model_spec=_spec())

    out = graph.invoke({"profile": _profile().model_dump()})

    rev = out["review"]
    assert rev["id"] == "review_prof_x" and rev["profile_id"] == "prof_x"   # harness-stamped
    assert rev["reviewer"] == "profile_reviewer@v1" and rev["generated_at"]
    assert rev["findings"][0]["id"] == "find_01"                            # finding id assigned
    assert rev["verdict"] == "needs_enrichment"
    done = next(p for et, p in events if et == "review.completed")
    assert done["blockers"] == 1 and done["findings"] == 1


def test_reviewer_no_profile_is_unsound(monkeypatch) -> None:
    graph = review_loop.build_reviewer_graph(_ctx(_Model(ReviewReport(id="x")), []), model_spec=_spec())
    out = graph.invoke({})
    assert out["review"]["verdict"] == "unsound"


def test_review_message_carries_grounding_signals_and_briefing() -> None:
    msg = build_review_message(_profile())
    assert "Machine grounding signals" in msg
    assert "HIGH-salience claims NOT deep-read" in msg and "c1" in msg  # flags the weak claim
    assert "Briefing" in msg and "Markets expect a hold" in msg         # the briefing view is included


def test_profile_reviewer_registered_with_fixture() -> None:
    from pathlib import Path

    from algent_backend.agent_system.agents.registry import default_agent_registry

    spec = default_agent_registry().get("profile_reviewer")
    assert spec.tool_ids == ()  # tool-free judgment
    assert spec.test_fixture is not None and spec.test_fixture.input_key == "profile"
    assert Path(spec.test_fixture.input_file).exists()
