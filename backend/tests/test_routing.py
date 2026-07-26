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

# -- promote order: rut-discounted weighted draw -------------------------------


def _grounded(title: str, thesis: str = "", score_tags: tuple[str, ...] = ()) -> ResearchVector:
    v = ResearchVector(
        title=title, thesis=thesis or f"thesis {title}", vector_type="story",
        rationale="because", research_effort="standard",
    )
    v.supporting_hits.append("gkg:story:x")   # something to research
    v.scope.extend(score_tags)
    return v


def _draw(ranking, by_id, **kw):
    from algent_backend.agent_system.agents.routing.promotion import apply_promotion_draw
    return apply_promotion_draw(ranking, by_id, **kw)


def test_draw_does_not_always_hand_the_lead_to_the_top_score() -> None:
    """A fixed criterion applied daily produces the same kind of winner daily. Odds are
    tilted by score, not decided by it."""
    by_id = {f"v{i}": _grounded(f"V{i}") for i in range(6)}
    ranking = RouteRanking(choices=[
        RankedChoice(candidate_id=f"v{i}", rank=i + 1, score=80 - i * 5) for i in range(6)
    ])

    leaders = {_draw(ranking, by_id, seed=s).choices[0].candidate_id for s in "abcdefgh"}
    assert len(leaders) > 1          # the lead genuinely moves
    for s in "abcdefgh":
        out = _draw(ranking, by_id, seed=s)
        assert sorted(c.candidate_id for c in out.choices) == sorted(by_id)


def test_draw_favours_the_higher_score_on_average() -> None:
    """Weighted, not flat: throwing the score away loses the one thing it is good for."""
    by_id = {"big": _grounded("Big"), "small": _grounded("Small")}
    ranking = RouteRanking(choices=[
        RankedChoice(candidate_id="big", rank=1, score=100),
        RankedChoice(candidate_id="small", rank=2, score=5),
    ])
    leads = sum(
        _draw(ranking, by_id, seed=str(n)).choices[0].candidate_id == "big"
        for n in range(80)
    )
    assert leads > 55   # ~95% expected by weight; assert well clear of a coin flip


def test_recurring_coverage_discounts_the_rut_without_banning_it() -> None:
    """The eighth Hormuz piece stops crowding the queue, but is never blocked."""
    by_id = {
        "rut": _grounded("Hormuz shipping risk again", "More on the Strait of Hormuz and Iran"),
        "fresh": _grounded("Exomoon candidate confirmed", "Astronomers report a first"),
    }
    ranking = RouteRanking(choices=[
        RankedChoice(candidate_id="rut", rank=1, score=88),
        RankedChoice(candidate_id="fresh", rank=2, score=40),
    ])
    recurring = (("subject:Strait of Hormuz", 4), ("place:Iran", 5))

    with_rut = sum(
        _draw(ranking, by_id, recurring=recurring, seed=str(n)).choices[0].candidate_id == "rut"
        for n in range(80)
    )
    without = sum(
        _draw(ranking, by_id, seed=str(n)).choices[0].candidate_id == "rut"
        for n in range(80)
    )
    assert with_rut < without          # recurrence really costs it the lead
    assert with_rut > 0                # but it is discounted, not banned


def test_break_glass_lets_an_enormous_new_story_lead_outright() -> None:
    """The cost of a flat lottery was leading with a solar record on the day a war starts."""
    by_id = {"huge": _grounded("Unprecedented new event"), **{
        f"v{i}": _grounded(f"V{i}") for i in range(5)}}
    ranking = RouteRanking(choices=[
        RankedChoice(candidate_id="huge", rank=1, score=97),
        *[RankedChoice(candidate_id=f"v{i}", rank=i + 2, score=60) for i in range(5)],
    ])
    for s in "abcdef":
        out = _draw(ranking, by_id, seed=s)
        assert out.choices[0].candidate_id == "huge"
    assert "break-glass" in _draw(ranking, by_id, seed="a").note


def test_break_glass_does_not_apply_to_a_story_we_keep_circling() -> None:
    """High score plus recurrence is exactly the rut — it must not get the override."""
    by_id = {"rut": _grounded("Iran strikes continue", "More on Iran"),
             "other": _grounded("Something else entirely")}
    ranking = RouteRanking(choices=[
        RankedChoice(candidate_id="rut", rank=1, score=99),
        RankedChoice(candidate_id="other", rank=2, score=30),
    ])
    notes = {_draw(ranking, by_id, recurring=(("place:Iran", 6),), seed=s).note for s in "ab"}
    assert all("break-glass" not in n for n in notes)


def test_draw_is_reproducible_for_one_portfolio() -> None:
    """Same portfolio, same queue — an operator can work down it across runs."""
    by_id = {f"v{i}": _grounded(f"V{i}") for i in range(6)}
    ranking = RouteRanking(choices=[
        RankedChoice(candidate_id=f"v{i}", rank=i + 1, score=50) for i in range(6)
    ])
    a = [c.candidate_id for c in _draw(ranking, by_id, seed="t0-20260725").choices]
    b = [c.candidate_id for c in _draw(ranking, by_id, seed="t0-20260725").choices]
    assert a == b


def test_draw_never_picks_a_cooled_or_ungroundable_vector() -> None:
    """The floor that survives: don't repeat ourselves, don't research nothing."""
    thin = ResearchVector(title="Nothing to read", thesis="t", vector_type="story",
                          rationale="r", research_effort="light")
    by_id = {"ok": _grounded("Fine"), "cooled": _grounded("Repeat"), "thin": thin}
    ranking = RouteRanking(choices=[
        RankedChoice(candidate_id="thin", rank=1, score=99),
        RankedChoice(candidate_id="cooled", rank=2, score=98, cooldown=True,
                     cooldown_reason="same family"),
        RankedChoice(candidate_id="ok", rank=3, score=10),
    ])

    out = _draw(ranking, by_id, seed="s")

    assert out.choices[0].candidate_id == "ok"
    assert top_vector(out, by_id).title == "Fine"


def test_draw_falls_back_to_the_ranking_when_nothing_is_eligible() -> None:
    thin = ResearchVector(title="A", thesis="t", vector_type="story", rationale="r",
                          research_effort="light")
    ranking = RouteRanking(choices=[RankedChoice(candidate_id="a", rank=1, score=5)])
    assert _draw(ranking, {"a": thin}, seed="s").choices[0].candidate_id == "a"


def test_operator_redo_clears_cooldown_so_a_published_piece_can_be_replaced() -> None:
    """A piece that shipped short of standard needs re-running, but its own headline cools it.
    The alternative to an escape hatch is deleting the article first, which loses the
    corrections trail."""
    from algent_backend.agent_system.agents.routing.promotion import clear_cooldown_for_redo

    ranking = RouteRanking(choices=[
        RankedChoice(candidate_id="v1", rank=1, score=80, cooldown=True,
                     cooldown_reason="same story-family as 'Typhoon Noul makes landfall'"),
    ])
    out = clear_cooldown_for_redo(ranking)

    assert out.choices[0].cooldown is False
    # Loud in the audit trail — a redo must never look like the ring having lapsed.
    assert "OPERATOR REDO" in out.note
    assert "same story-family" in out.choices[0].cooldown_reason   # original reason retained


def test_redo_is_off_by_default(monkeypatch) -> None:
    from algent_backend.agent_system.agents.routing.promotion import redo_enabled

    monkeypatch.delenv("ALGENT_PROMOTE_REDO", raising=False)
    assert redo_enabled() is False
    monkeypatch.setenv("ALGENT_PROMOTE_REDO", "1")
    assert redo_enabled() is True
