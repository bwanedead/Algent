"""Tests for the runnable signal_router agent (t1 -> t2 promotion graph)."""

from __future__ import annotations

from algent_backend.agent_system.agents.discovery.portfolio import (
    ResearchPortfolio,
    ResearchVector,
    ensure_vector_ids,
)
from algent_backend.agent_system.agents.routing.contracts import RankedChoice, RouteRanking
from algent_backend.agent_system.agents.routing.run_graph import build_signal_router_graph
from algent_backend.agent_system.foundation.models import ModelSpec
from algent_backend.agent_system.runs.context import AgentRunContext


class _Structured:
    def __init__(self, ranking):
        self._r = ranking

    def invoke(self, _messages, config=None):
        return self._r


class _Model:
    def __init__(self, ranking):
        self._r = ranking

    def with_structured_output(self, _schema):
        return _Structured(self._r)


class _Resolver:
    def __init__(self, model):
        self._m = model

    def resolve(self, _spec):
        return type("R", (), {"client": self._m})()


def _ctx(model, events):
    return AgentRunContext(
        run_id="t",
        model_resolver=_Resolver(model),  # type: ignore[arg-type]
        emit=lambda et, p=None: events.append((et, p or {})),
    )


def _portfolio() -> ResearchPortfolio:
    return ensure_vector_ids(ResearchPortfolio(generated_at="t", vectors=[
        ResearchVector(title="Quiet local item", thesis="t0", vector_type="story", rationale="r", research_effort="light"),
        ResearchVector(title="Major escalation", thesis="t1", vector_type="story", rationale="r", research_effort="deep"),
    ]))


def test_router_graph_ranks_and_selects_top() -> None:
    portfolio = _portfolio()
    big = portfolio.vectors[1].id  # the model ranks "Major escalation" #1
    small = portfolio.vectors[0].id
    ranking = RouteRanking(choices=[
        RankedChoice(candidate_id=big, rank=1, score=92, rationale="highest stakes"),
        RankedChoice(candidate_id=small, rank=2, score=40, rationale="minor"),
    ])
    events: list = []
    graph = build_signal_router_graph(_ctx(_Model(ranking), events), model_spec=_spec())

    out = graph.invoke({"portfolio": portfolio.model_dump()})

    assert out["selected_vector"]["title"] == "Major escalation"   # programmatic #1 pick
    assert out["ranking"]["choices"][0]["candidate_id"] == big
    assert any(et == "output.preview" for et, _ in events)         # surfaced to the timeline


def test_router_graph_handles_no_portfolio() -> None:
    events: list = []
    graph = build_signal_router_graph(_ctx(_Model(RouteRanking()), events), model_spec=_spec())
    out = graph.invoke({})
    assert "selected_vector" not in out                            # nothing to select
    assert any(et == "signal_router.no_input" for et, _ in events)


def test_signal_router_registered_with_fixture() -> None:
    from algent_backend.agent_system.agents.registry import default_agent_registry

    spec = default_agent_registry().get("signal_router")
    assert spec.tool_ids == () and spec.search_channels is None     # pure judgment, no tools
    assert spec.test_fixture is not None and spec.test_fixture.input_key == "portfolio"


def _spec():
    return ModelSpec(provider="openai", model="gpt-5.4-mini")
