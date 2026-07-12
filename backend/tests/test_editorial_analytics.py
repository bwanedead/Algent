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
    return ModelSpec(provider="openai", model="gpt-5.4-nano")


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
    # A request whose data_refs don't resolve is not a request; if none survive, not warranted.
    plan = AnalyticsPlan(id="", warranted=True, requests=[
        AnalyticsRequest(id="", kind="chart", data_refs=["c_ghost"], spec="x")])
    graph = ar.build_analytics_router_graph(_ctx(_Model(plan), []), model_spec=_spec())
    p = graph.invoke({"profile": _profile().model_dump()})["analytics_plan"]
    assert p["warranted"] is False and p["requests"] == []


def test_router_no_profile_is_not_warranted() -> None:
    graph = ar.build_analytics_router_graph(_ctx(_Model(AnalyticsPlan(id="x")), []), model_spec=_spec())
    assert graph.invoke({})["analytics_plan"]["warranted"] is False


def test_analytics_router_registered_with_fixture() -> None:
    from pathlib import Path

    from algent_backend.agent_system.agents.registry import default_agent_registry

    spec = default_agent_registry().get("analytics_router")
    assert spec.default_model.model == "gpt-5.4-nano" and spec.test_fixture is not None
    assert Path(spec.test_fixture.input_file).exists()
