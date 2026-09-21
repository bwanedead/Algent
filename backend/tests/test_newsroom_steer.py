"""Operator steer — reframe a live run without throwing away its research."""

from __future__ import annotations

from pathlib import Path

from algent_backend.agent_system.agents.newsroom import steer
from algent_backend.agent_system.agents.research.briefing import render_briefing
from algent_backend.agent_system.agents.research.profile import SignalProfile


def test_a_steer_lands_in_the_run_and_stays_there(tmp_path: Path) -> None:
    pending, run = tmp_path / "pending.jsonl", tmp_path / "run" / "artifacts"
    steer.add("read it as strategy", path=pending)

    landed = steer.drain(run, stage="gauntlet", path=pending)
    assert [e["text"] for e in landed] == ["read it as strategy"]
    assert steer.pending(path=pending) == []                       # consumed once
    assert steer.for_run(run) == ["read it as strategy"]           # and persisted with the run
    # A second drain with nothing queued changes nothing — resume reads the same record.
    assert steer.drain(run, stage="editorial", path=pending) == []
    assert steer.for_run(run) == ["read it as strategy"]


def test_steers_accumulate_in_order(tmp_path: Path) -> None:
    pending, run = tmp_path / "p.jsonl", tmp_path / "a"
    steer.add("first", path=pending)
    steer.drain(run, stage="profile", path=pending)
    steer.add("second", path=pending)
    steer.drain(run, stage="editorial", path=pending)
    assert steer.for_run(run) == ["first", "second"]


def test_research_sees_it_beside_the_thesis() -> None:
    v = steer.apply_to_vector({"title": "t", "thesis": "establish the deal"}, ["who gains leverage"])
    assert v["thesis"].startswith("establish the deal") and "who gains leverage" in v["thesis"]
    assert steer.apply_to_vector({"thesis": "x"}, []) == {"thesis": "x"}


def test_every_later_stage_reads_it_first_and_as_framing_not_evidence() -> None:
    p = SignalProfile.model_validate(steer.apply_to_profile(
        {"id": "p", "title": "Greenland", "summary": "the gist"}, ["read it as strategy"]))
    brief = render_briefing(p)
    assert brief.index("Operator steer") < brief.index("the gist")
    assert "read it as strategy" in brief and "not evidence" in brief


def test_an_empty_steer_is_refused(tmp_path: Path) -> None:
    import pytest

    with pytest.raises(ValueError):
        steer.add("   ", path=tmp_path / "p.jsonl")


def test_a_story_with_no_vector_id_still_gets_its_own_profile() -> None:
    # Every brief used to become prof_unknown, and each saved over the last in the store.
    from algent_backend.agent_system.agents.research.assembly import _profile_id

    a = _profile_id({"id": "", "title": "Megaprojects"})
    b = _profile_id({"id": "", "title": "Greenland deal"})
    assert a != b and "unknown" not in a
    assert _profile_id({"id": "vec_42"}) == "prof_42"


def test_a_brief_carries_a_stable_id() -> None:
    from algent_backend.cli.newsroom.pipeline import ad_hoc_vector

    v = ad_hoc_vector("What the Greenland deal buys, and what it costs")
    assert v["id"].startswith("brief_what_the_greenland_deal")
