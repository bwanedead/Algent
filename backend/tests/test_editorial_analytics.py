"""Tests for the analytics_router — grounded, honest analytics requests (or none)."""

from __future__ import annotations

from algent_backend.agent_system.agents.editorial import analytics_router as ar
from algent_backend.agent_system.agents.editorial.analytics_contracts import (
    AnalyticsPlan,
    AnalyticsRequest,
)
from algent_backend.agent_system.agents.research.profile import Claim, SignalProfile, SourceArtifact
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


def _profile() -> SignalProfile:
    return SignalProfile(
        id="prof_x", title="Fed path",
        source_ledger=[SourceArtifact(id="s1", url="u")],
        claim_ledger=[Claim(id="c1", text="core PCE rose 3.4%", supported_by=["s1"])],
    )


def test_router_emits_grounded_requests_and_stamps_identity() -> None:
    plan = AnalyticsPlan(id="", warranted=True, requests=[
        AnalyticsRequest(id="", kind="chart", title="PCE trend", question="how is inflation moving?",
                         spec="line chart of PCE y/y", data_refs=["c1", "c_ghost"], rationale="shows the trend")])
    events: list = []
    graph = ar.build_analytics_router_graph(_ctx(_Model(plan), events), model_spec=_spec())
    out = graph.invoke({"profile": _profile().model_dump()})

    p = AnalyticsPlan.model_validate(out["analytics_plan"])
    assert p.id == "analytics_prof_x" and p.warranted is True and p.generator == "analytics_router@v1"
    assert p.requests[0].id == "anx_01"
    assert p.requests[0].data_refs == ["c1"]   # c_ghost dropped — no ungrounded analytics
    done = next(pl for et, pl in events if et == "analytics.completed")
    assert done["warranted"] is True and done["requests"] == 1


def test_router_drops_a_request_grounded_in_nothing() -> None:
    # A request whose data_refs don't resolve and is not may_source is not a request.
    plan = AnalyticsPlan(id="", warranted=True, requests=[
        AnalyticsRequest(id="", kind="chart", data_refs=["c_ghost"], spec="x")])
    graph = ar.build_analytics_router_graph(_ctx(_Model(plan), []), model_spec=_spec())
    p = graph.invoke({"profile": _profile().model_dump()})["analytics_plan"]
    assert p["warranted"] is False and p["requests"] == []


def test_router_keeps_may_source_without_profile_series() -> None:
    # Profile need not hold a multi-row series — usefulness + a source hunch is enough.
    plan = AnalyticsPlan(id="", warranted=True, requests=[
        AnalyticsRequest(
            id="", kind="chart",
            title="Weekly confirmed cases",
            question="Is the outbreak accelerating?",
            spec="line of weekly confirmed cases last 8 weeks",
            data_refs=[],
            may_source=True,
            source_hint="WHO / MoH weekly Ebola case counts for DRC, last 8 weeks",
            rationale="trajectory the prose alone cannot show"),
    ])
    graph = ar.build_analytics_router_graph(_ctx(_Model(plan), []), model_spec=_spec())
    p = graph.invoke({"profile": _profile().model_dump()})["analytics_plan"]
    assert p["warranted"] is True and len(p["requests"]) == 1
    req = p["requests"][0]
    assert req["may_source"] is True
    assert "WHO" in req["source_hint"]
    assert req["data_refs"] == []


def test_router_may_source_falls_back_to_spec_as_hint() -> None:
    plan = AnalyticsPlan(id="", warranted=True, requests=[
        AnalyticsRequest(id="", kind="chart", may_source=True, spec="BLS core PCE y/y last 12 months",
                         title="PCE path", question="trend", data_refs=[])])
    graph = ar.build_analytics_router_graph(_ctx(_Model(plan), []), model_spec=_spec())
    p = graph.invoke({"profile": _profile().model_dump()})["analytics_plan"]
    assert p["warranted"] is True
    assert "BLS" in p["requests"][0]["source_hint"]


def test_router_drops_meta_evidence_ledger_tables() -> None:
    # Live failure: every article got a 2-col "confirmed vs unconfirmed" / claim-support notebook.
    plan = AnalyticsPlan(id="", warranted=True, requests=[
        AnalyticsRequest(
            id="", kind="table",
            title="Confirmed vs unconfirmed retaliation levers",
            question="Which tools are confirmed first-party vs secondary?",
            spec="two-column evidence type status grid",
            data_refs=["c1"],
            rationale="reconcile claim status for the reader"),
        AnalyticsRequest(
            id="", kind="insight",
            title="What the exemption rationale does and doesn't prove",
            question="Does the claim ledger support inflation targeting?",
            spec="bucket support in claims",
            data_refs=["c1"],
            rationale="evidence-grade share of claims"),
        AnalyticsRequest(
            id="", kind="chart",
            title="Share of exports at risk",
            question="What share of exports faces the tariff?",
            spec="bar of 18% vs exempt categories",
            data_refs=["c1"],
            rationale="shows scale"),
    ])
    graph = ar.build_analytics_router_graph(_ctx(_Model(plan), []), model_spec=_spec())
    p = graph.invoke({"profile": _profile().model_dump()})["analytics_plan"]
    assert p["warranted"] is True
    assert len(p["requests"]) == 1
    assert p["requests"][0]["kind"] == "chart"
    assert "Share of exports" in p["requests"][0]["title"]


def test_router_no_profile_is_not_warranted() -> None:
    graph = ar.build_analytics_router_graph(_ctx(_Model(AnalyticsPlan(id="x")), []), model_spec=_spec())
    assert graph.invoke({})["analytics_plan"]["warranted"] is False


def test_router_defers_source_specimen_until_licensed_lane() -> None:
    plan = AnalyticsPlan(id="", warranted=True, requests=[
        AnalyticsRequest(
            id="", kind="image", title="Linear A tablet", question="what does the script look like?",
            spec="photograph of a Linear A tablet", data_refs=["c1"],
            visual_class="source_specimen", priority="essential_context",
            rationale="reader needs to see the artifact",
        ),
        AnalyticsRequest(
            id="", kind="chart", title="PCE trend", question="how is inflation moving?",
            spec="line chart of PCE y/y", data_refs=["c1"], visual_class="data_chart",
        ),
    ])
    graph = ar.build_analytics_router_graph(_ctx(_Model(plan), []), model_spec=_spec())
    p = AnalyticsPlan.model_validate(graph.invoke({"profile": _profile().model_dump()})["analytics_plan"])
    assert p.warranted is True
    by_class = {r.visual_class: r for r in p.requests}
    assert by_class["source_specimen"].status == "source_unavailable"
    assert "licensed media" in by_class["source_specimen"].rationale
    assert by_class["data_chart"].status == "requested"
    assert "source_specimen" in p.note


def test_analytics_router_registered_with_fixture() -> None:
    from pathlib import Path

    from algent_backend.agent_system.agents.registry import default_agent_registry

    spec = default_agent_registry().get("analytics_router")
    assert spec.default_model.provider == "meta" and spec.default_model.model == "muse-spark-1.2-contributor" and spec.test_fixture is not None
    assert Path(spec.test_fixture.input_file).exists()
