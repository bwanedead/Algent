"""Absolute votes: every reader's history-free view is kept and shown to the next, never applied alone."""

from __future__ import annotations

from algent_backend.agent_system.agents.pulse import Influence, Pulse, PulseDefinition, Source
from algent_backend.agent_system.agents.pulse.framing import describe
from algent_backend.agent_system.agents.pulse.projection import VOTES, absolute_votes, project


def _inf(n: int, *, pos=None, absolute=None, profile="", mode="article") -> Influence:
    return Influence(pulse_id="pls_x", at=f"2026-09-{n:02d}T00:00:00+00:00", mode=mode, definition_version=1,
                     proposed_position=pos, absolute_position=absolute,
                     decision="applied" if pos is not None else "no_change", rationale=f"r{n}",
                     source=Source(run_id=f"run{n}", profile_id=profile))


def test_a_vote_far_from_the_history_does_not_move_the_pulse() -> None:
    log = [_inf(1, pos=60, mode="seed"), _inf(2, absolute=20, profile="p1")]
    state = project("pls_x", log)
    assert state.position == 60 and state.absolute_view == 20 and state.absolute_voters == 1


def test_one_research_effort_is_one_voter_and_only_recent_voters_count() -> None:
    log = [_inf(1, pos=60, mode="seed")]
    log += [_inf(2, absolute=10, profile="p1"), _inf(3, absolute=40, profile="p1")]   # p1 revised its view
    log += [_inf(4 + n, absolute=50, profile=f"q{n}") for n in range(VOTES)]
    votes = absolute_votes(log)
    assert len(votes) == VOTES and all(v.source.profile_id != "p1" for v in votes)
    assert project("pls_x", log).absolute_view == 50


def test_newer_votes_count_for_more_but_one_vote_does_not_decide() -> None:
    log = [_inf(1, pos=60, mode="seed")]
    old = [_inf(2 + n, absolute=30, profile=f"old{n}") for n in range(3)]
    assert project("pls_x", log + old + [_inf(9, absolute=70, profile="new")]).absolute_view == 30
    newer = [_inf(9 + n, absolute=70, profile=f"new{n}") for n in range(2)]
    assert project("pls_x", log + old + newer).absolute_view == 70     # 2 newer outweigh 3 older


def test_blind_reads_are_not_votes() -> None:
    log = [_inf(1, pos=60, mode="seed"), _inf(2, pos=10, absolute=10, mode="blind")]
    assert absolute_votes(log) == []


def test_every_reader_sees_the_other_readers_votes() -> None:
    pulse = Pulse(id="pls_x", situation_id="sit_x", name="Tension",
                  definitions=[PulseDefinition(question="q", low_end="calm", high_end="war")])
    log = [_inf(1, pos=60, mode="seed"), _inf(2, absolute=40, profile="p1"), _inf(3, absolute=44, profile="p2")]
    text = describe(pulse, log)
    assert "ABSOLUTE VOTES" in text and "more: 44" in text and "holds 60" in text
    assert "ABSOLUTE VOTES" not in describe(pulse, log, blind=True)
