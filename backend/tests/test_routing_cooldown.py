"""Agent-semantic cooldown — flags on ranking choices; no lexical demotion floor."""

from __future__ import annotations

from algent_backend.agent_system.agents.discovery.portfolio import (
    ResearchPortfolio,
    ResearchVector,
    ensure_vector_ids,
)
from algent_backend.agent_system.agents.routing.contracts import (
    RankedChoice,
    RouteCandidate,
    RouteRanking,
    RoutingBrief,
)
from algent_backend.agent_system.agents.routing.engine import route
from algent_backend.agent_system.agents.routing.promotion import rank_portfolio, top_vector
from algent_backend.agent_system.agents.routing.prompts import build_router_message
from algent_backend.agent_system.foundation.models import ModelSpec
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


def _spec():
    return ModelSpec(provider="openai", model="gpt-5.4-mini")


def test_router_message_carries_headlines_for_semantic_cooldown() -> None:
    msg = build_router_message(
        [RouteCandidate(id="v1", label="x", summary="y")],
        RoutingBrief(
            role="r",
            candidate_kind="k",
            selecting_for="s",
            downstream="d",
            recent=(("2026-07-18", "Hormuz disruption"),),
        ),
    )
    assert "ALREADY COVERED" in msg and "Hormuz disruption" in msg
    assert "cooldown=true" in msg.lower() or "cooldown=true/false" in msg.lower() or "cooldown=true" in msg
    assert "SEMANTICALLY" in msg
    assert "mechanical floor" not in msg


def test_top_vector_skips_agent_cooldown_flags() -> None:
    portfolio = ensure_vector_ids(ResearchPortfolio(generated_at="t", vectors=[
        ResearchVector(title="ICE again", thesis="t", vector_type="story",
                       rationale="r", research_effort="deep"),
        ResearchVector(title="Ortega elections", thesis="t", vector_type="story",
                       rationale="r", research_effort="standard"),
    ]))
    ice, ort = portfolio.vectors[0].id, portfolio.vectors[1].id
    ranking = RouteRanking(choices=[
        RankedChoice(candidate_id=ice, rank=1, score=95, cooldown=True,
                     cooldown_reason="prior ICE piece"),
        RankedChoice(candidate_id=ort, rank=2, score=80, cooldown=False),
    ])
    # Simulate engine band: free first
    ranking = ranking.model_copy(update={"choices": [
        RankedChoice(candidate_id=ort, rank=1, score=80, cooldown=False),
        RankedChoice(candidate_id=ice, rank=2, score=95, cooldown=True,
                     cooldown_reason="prior ICE piece"),
    ]})
    by_id = {v.id: v for v in portfolio.vectors}
    top = top_vector(ranking, by_id)
    assert top is not None and top.title == "Ortega elections"


def test_route_ranks_all_and_backfills_missing() -> None:
    ranking = RouteRanking(choices=[
        RankedChoice(candidate_id="a", rank=1, score=90, cooldown=False),
        # model forgot b
    ])
    events: list = []
    ctx = _ctx(_Model(ranking, []), events)
    brief = RoutingBrief(
        role="r", candidate_kind="k", selecting_for="s", downstream="d", rank_all=True,
    )
    out = route(
        ctx,
        [RouteCandidate(id="a", label="A"), RouteCandidate(id="b", label="B")],
        brief,
        model_spec=_spec(),
    )
    ids = {c.candidate_id for c in out.choices}
    assert ids == {"a", "b"}
    assert out.choices[0].candidate_id == "a"


def test_route_puts_cooldown_band_after_free() -> None:
    ranking = RouteRanking(choices=[
        RankedChoice(candidate_id="cooled", rank=1, score=99, cooldown=True,
                     cooldown_reason="prior"),
        RankedChoice(candidate_id="fresh", rank=2, score=70, cooldown=False),
    ])
    ctx = _ctx(_Model(ranking, []), [])
    brief = RoutingBrief(
        role="r", candidate_kind="k", selecting_for="s", downstream="d", rank_all=True,
        recent=(("2026-07-22", "Prior story"),),
    )
    out = route(
        ctx,
        [
            RouteCandidate(id="cooled", label="Same family"),
            RouteCandidate(id="fresh", label="New story"),
        ],
        brief,
        model_spec=_spec(),
    )
    assert out.choices[0].candidate_id == "fresh"
    assert out.choices[0].cooldown is False
    assert out.choices[1].candidate_id == "cooled"
    assert out.choices[1].cooldown is True
    assert "agent cooldown" in out.note
