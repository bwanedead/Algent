"""Tests for the generic routing engine and the t1->t2 promotion router."""

from __future__ import annotations

from algent_backend.agent_system.agents.discovery.portfolio import (
    ResearchPortfolio,
    ResearchVector,
)
from algent_backend.agent_system.agents.routing import (
    PROMOTION_BRIEF,
    RankedChoice,
    RouteCandidate,
    RouteRanking,
    rank_portfolio,
    route,
    top_vector,
)
from algent_backend.agent_system.agents.routing.engine import ROUTING_DECISION
from algent_backend.agent_system.agents.routing.prompts import build_router_system_prompt
from algent_backend.agent_system.runs.context import AgentRunContext


class _Structured:
    def __init__(self, ranking: RouteRanking, capture: list) -> None:
        self._r, self._cap = ranking, capture

    def invoke(self, messages, config=None):
        self._cap.append(messages)
        return self._r


class _Model:
    def __init__(self, ranking: RouteRanking, capture: list) -> None:
        self._r, self._cap = ranking, capture

    def with_structured_output(self, _schema):
        return _Structured(self._r, self._cap)


class _Resolver:
    def __init__(self, model) -> None:
        self._m = model

    def resolve(self, _spec):
        return type("R", (), {"client": self._m})()


def _ctx(model, events: list):
    return AgentRunContext(
        run_id="t",
        model_resolver=_Resolver(model),  # type: ignore[arg-type]
        emit=lambda et, p=None: events.append((et, p or {})),
    )


def _vec(title: str, effort: str = "standard") -> ResearchVector:
    return ResearchVector(
        title=title, thesis=f"thesis {title}", vector_type="story",
        rationale="because", research_effort=effort,
    )


def test_route_filters_unknown_ids_sorts_by_rank_and_emits() -> None:
    ranking = RouteRanking(choices=[
        RankedChoice(candidate_id="b", rank=2, score=70),
        RankedChoice(candidate_id="a", rank=1, score=90),
        RankedChoice(candidate_id="ghost", rank=3, score=50),  # not a real candidate
    ])
    events: list = []
    ctx = _ctx(_Model(ranking, []), events)
    cands = [RouteCandidate(id="a", label="A"), RouteCandidate(id="b", label="B")]

    out = route(ctx, cands, PROMOTION_BRIEF, model_spec=_spec())

    assert [c.candidate_id for c in out.choices] == ["a", "b"]  # ghost dropped, rank-ordered
    assert events and events[0][0] == ROUTING_DECISION and events[0][1]["considered"] == 2


def test_route_no_candidates_skips_model() -> None:
    calls: list = []
    ctx = _ctx(_Model(RouteRanking(), calls), [])
    out = route(ctx, [], PROMOTION_BRIEF, model_spec=_spec())
    assert out.choices == [] and calls == []  # never called the model


def test_rank_portfolio_wraps_vectors_and_top_vector_picks_number_one() -> None:
    portfolio = ResearchPortfolio(generated_at="t", vectors=[_vec("V0", "light"), _vec("V1", "deep")])
    ranking = RouteRanking(choices=[
        RankedChoice(candidate_id="vec:01", rank=1, score=95),
        RankedChoice(candidate_id="vec:00", rank=2, score=60),
    ])
    captured: list = []
    ctx = _ctx(_Model(ranking, captured), [])

    rk, by_id = rank_portfolio(ctx, portfolio, model_spec=_spec())
    top = top_vector(rk, by_id)

    assert top is not None and top.title == "V1"  # #1 maps back to the right vector
    # the candidate rendering reached the model (V1's signals are in the human message)
    assert "vec:01" in captured[0][1].content


def test_router_prompt_injects_brief_and_system_map() -> None:
    sys = build_router_system_prompt(PROMOTION_BRIEF)
    assert "Algent newsroom" in sys          # self-awareness layer present
    assert "signal profile" in sys           # knows the downstream
    assert "promotion editor" in sys         # the injected role


def _spec():
    from algent_backend.agent_system.foundation.models import ModelSpec
    return ModelSpec(provider="openai", model="gpt-5.4-mini")
