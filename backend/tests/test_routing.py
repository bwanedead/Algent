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
        RankedChoice(candidate_id="vec:01", rank=1, score=95, cooldown=False),
        RankedChoice(candidate_id="vec:00", rank=2, score=60, cooldown=False),
    ])
    captured: list = []
    ctx = _ctx(_Model(ranking, captured), [])

    rk, by_id = rank_portfolio(ctx, portfolio, model_spec=_spec())
    top = top_vector(rk, by_id)

    assert top is not None and top.title == "V1"  # #1 maps back to the right vector
    # the candidate rendering reached the model (V1's signals are in the human message)
    assert "vec:01" in captured[0][1].content
    # full-list + agent cooldown instructions in the message
    human = captured[0][1].content
    assert "Rank ALL" in human or "ALL" in human


def test_router_prompt_injects_brief_and_system_map() -> None:
    sys = build_router_system_prompt(PROMOTION_BRIEF)
    assert "Algent newsroom" in sys          # self-awareness layer present
    assert "signal profile" in sys           # knows the downstream
    assert "promotion editor" in sys         # the injected role


def _spec():
    from algent_backend.agent_system.foundation.models import ModelSpec
    return ModelSpec(provider="openai", model="gpt-5.4-mini")


# -- promote order: lottery over the eligible, not a score ---------------------


def _grounded(title: str) -> ResearchVector:
    v = _vec(title)
    v.supporting_hits.append("gkg:story:x")   # something to research
    return v


def test_lottery_ignores_the_score_when_ordering_the_promotable() -> None:
    """The composite score manufactured the rut it was meant to avoid: its first five
    criteria are all monotonic in 'how big is this conflict', so the same kind of story
    won every day. Order among the eligible is chance now."""
    from algent_backend.agent_system.agents.routing.promotion import apply_promotion_lottery

    by_id = {f"v{i}": _grounded(f"V{i}") for i in range(8)}
    ranking = RouteRanking(choices=[
        RankedChoice(candidate_id=f"v{i}", rank=i + 1, score=100 - i) for i in range(8)
    ])

    orders = {
        tuple(c.candidate_id for c in apply_promotion_lottery(ranking, by_id, seed=s).choices)
        for s in ("a", "b", "c", "d", "e")
    }
    assert len(orders) > 1                       # the draw actually varies
    for order in orders:
        assert sorted(order) == sorted(by_id)    # and never loses a vector


def test_lottery_is_reproducible_for_one_portfolio() -> None:
    """Same portfolio, same queue — so an operator can work down it across runs."""
    from algent_backend.agent_system.agents.routing.promotion import apply_promotion_lottery

    by_id = {f"v{i}": _grounded(f"V{i}") for i in range(6)}
    ranking = RouteRanking(choices=[
        RankedChoice(candidate_id=f"v{i}", rank=i + 1, score=50) for i in range(6)
    ])
    first = apply_promotion_lottery(ranking, by_id, seed="t0-20260725")
    again = apply_promotion_lottery(ranking, by_id, seed="t0-20260725")

    assert [c.candidate_id for c in first.choices] == [c.candidate_id for c in again.choices]


def test_lottery_never_draws_a_cooled_or_ungroundable_vector() -> None:
    """The floor that survives: don't repeat ourselves, and don't research nothing."""
    from algent_backend.agent_system.agents.routing.promotion import apply_promotion_lottery

    by_id = {"ok": _grounded("Fine"), "cooled": _grounded("Repeat"), "thin": _vec("Nothing to read")}
    ranking = RouteRanking(choices=[
        RankedChoice(candidate_id="thin", rank=1, score=99),
        RankedChoice(candidate_id="cooled", rank=2, score=98, cooldown=True,
                     cooldown_reason="same family"),
        RankedChoice(candidate_id="ok", rank=3, score=10),
    ])

    out = apply_promotion_lottery(ranking, by_id, seed="s")

    assert out.choices[0].candidate_id == "ok"      # the only eligible one leads
    assert top_vector(out, by_id).title == "Fine"   # and it is what gets promoted
    assert "lottery" in out.note


def test_lottery_falls_back_to_the_ranking_when_nothing_is_eligible() -> None:
    from algent_backend.agent_system.agents.routing.promotion import apply_promotion_lottery

    by_id = {"a": _vec("A")}   # ungroundable
    ranking = RouteRanking(choices=[RankedChoice(candidate_id="a", rank=1, score=5)])
    assert apply_promotion_lottery(ranking, by_id, seed="s").choices[0].candidate_id == "a"
