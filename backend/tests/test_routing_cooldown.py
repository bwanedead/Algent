"""Mechanical story-family cooldown — the floor that soft 'close match' instruction failed to hold."""

from __future__ import annotations

from algent_backend.agent_system.agents.routing.contracts import RankedChoice, RouteCandidate, RouteRanking
from algent_backend.agent_system.agents.routing.cooldown import anchors, cooled_by, demote_cooled, significant_tokens
from algent_backend.agent_system.agents.routing.prompts import build_router_message


_HORMUZ_PRIORS = [
    "Strait of Hormuz impaired, not closed: strikes and vessel damage reduce traffic",
    "Strait of Hormuz sees severe disruption as tankers are hit and traffic drops",
    "Hormuz saw serious traffic disruption, but the record doesn't prove a sustained full closure",
]


def test_hormuz_reframe_is_cooled_by_anchor() -> None:
    # Live failure mode: router re-titled the beat as "war widens / IRGC" and promoted it.
    blob = (
        "U.S.–Iran war widens with strikes on Revolutionary Guard and Hormuz disruption "
        "reports Iran conflict widening with strikes on IRGC assets and Hormuz disruption"
    )
    cool, why = cooled_by(blob, _HORMUZ_PRIORS)
    assert cool, why
    assert "hormuz" in why.lower() or "strikes" in why.lower() or "saturated" in why.lower()


def test_kyiv_story_not_cooled_by_hormuz_priors() -> None:
    cool, why = cooled_by(
        "Kyiv under heavy missile/drone attack amid Patriot shortage — air defense procurement",
        _HORMUZ_PRIORS,
    )
    assert not cool, why


def test_generic_news_words_are_not_anchors() -> None:
    # Live false positives on run 0009: "active" (SharePoint) demoted SonicWall; "damage"
    # (Hormuz) demoted a Peru earthquake. Common verbs/adjectives must never be family keys.
    assert "active" not in anchors("CISA warns active exploitation of SharePoint Server")
    assert "damage" not in anchors("vessel damage reduce traffic in the strait")
    cool, why = cooled_by(
        "Actively exploited SonicWall SMA1000 zero-days hit enterprise gateways",
        ["CISA warns SharePoint Server are under active exploitation"],
    )
    assert not cool, why
    cool2, why2 = cooled_by(
        "Peru earthquake with deaths and infrastructure damage",
        ["Strait of Hormuz impaired: strikes and vessel damage reduce traffic"],
    )
    assert not cool2, why2


def test_sharepoint_second_piece_cooled_by_anchor() -> None:
    priors = [
        "CISA warns SharePoint Server Subscription Edition, 2019, and 2016 are under active exploitation",
    ]
    cool, why = cooled_by(
        "Microsoft/SharePoint exploitation campaign becomes a broad enterprise security story",
        priors,
    )
    assert cool and "sharepoint" in why.lower()


def test_demote_moves_cooled_below_fresh() -> None:
    recent = tuple((f"2026-07-1{i}", t) for i, t in enumerate(_HORMUZ_PRIORS))
    candidates = [
        RouteCandidate(id="rv1", label="U.S.–Iran war widens with Hormuz disruption",
                       summary="IRGC strikes and shipping pressure"),
        RouteCandidate(id="rv4", label="Kyiv under heavy missile attack",
                       summary="Patriot shortage constrains defense"),
        RouteCandidate(id="rv8", label="China consumer defaults rise",
                       summary="household credit stress"),
    ]
    # LLM put Hormuz first (the live bug); floor must promote a fresh story.
    ranking = RouteRanking(choices=[
        RankedChoice(candidate_id="rv1", rank=1, score=93, rationale="biggest impact"),
        RankedChoice(candidate_id="rv4", rank=2, score=74, rationale="human impact"),
        RankedChoice(candidate_id="rv8", rank=3, score=47, rationale="macro"),
    ])
    out = demote_cooled(ranking, candidates, recent)
    assert out.choices[0].candidate_id == "rv4"
    assert out.choices[0].rank == 1
    assert out.choices[-1].candidate_id == "rv1"
    assert "mechanical cooldown" in out.note


def test_demote_noop_when_all_cooled() -> None:
    # Nowhere to demote to — leave LLM order rather than empty promote.
    recent = (("2026-07-18", "Hormuz traffic falls"),)
    candidates = [
        RouteCandidate(id="a", label="Hormuz again", summary="strait traffic"),
        RouteCandidate(id="b", label="Hormuz closure debate", summary="shipping"),
    ]
    ranking = RouteRanking(choices=[
        RankedChoice(candidate_id="a", rank=1, score=90),
        RankedChoice(candidate_id="b", rank=2, score=80),
    ])
    out = demote_cooled(ranking, candidates, recent)
    assert [c.candidate_id for c in out.choices] == ["a", "b"]


def test_significant_tokens_drop_glue() -> None:
    toks = significant_tokens("The Strait of Hormuz sees severe disruption as the tankers are hit")
    assert "hormuz" in toks and "strait" in toks and "disruption" in toks
    assert "the" not in toks and "sees" not in toks
    assert "hormuz" in anchors("Strait of Hormuz traffic")


def test_router_message_names_reframe_failure() -> None:
    msg = build_router_message(
        [RouteCandidate(id="v1", label="x", summary="y")],
        10,
        (("2026-07-18", "Hormuz disruption"),),
    )
    assert "STORY-FAMILY" in msg and "REFRAME IS NOT A NEW STORY" in msg
    assert "mechanical floor" in msg
