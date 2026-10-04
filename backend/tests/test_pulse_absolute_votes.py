"""Absolute reads: recorded at their moment and shown in the trace; never applied, never pooled."""

from __future__ import annotations

from algent_backend.agent_system.agents.pulse import Influence, Pulse, PulseDefinition, Source
from algent_backend.agent_system.agents.pulse.framing import describe
from algent_backend.agent_system.agents.pulse.projection import project


def _inf(n: int, *, pos=None, absolute=None, mode="article") -> Influence:
    return Influence(pulse_id="pls_x", at=f"2026-09-{n:02d}T00:00:00+00:00", mode=mode, definition_version=1,
                     proposed_position=pos, absolute_position=absolute,
                     decision="applied" if pos is not None else "no_change", rationale=f"r{n}",
                     source=Source(run_id=f"run{n}"))


def test_an_absolute_read_never_moves_the_pulse() -> None:
    assert project("pls_x", [_inf(1, pos=60, mode="seed"), _inf(2, absolute=20)]).position == 60


def test_the_newest_reading_is_the_state_however_far_the_world_moved() -> None:
    log = [_inf(1, pos=5, absolute=5, mode="seed"), _inf(2, pos=30, absolute=30), _inf(3, pos=90, absolute=90)]
    assert project("pls_x", log).position == 90        # old calm readings do not drag a war down


def test_each_readers_sense_of_reality_shows_in_the_trace_at_its_date() -> None:
    pulse = Pulse(id="pls_x", situation_id="sit_x", name="Tension",
                  definitions=[PulseDefinition(question="q", low_end="calm", high_end="war")])
    log = [_inf(1, pos=60, mode="seed"), _inf(2, pos=62, absolute=45)]
    text = describe(pulse, log)
    assert "2026-09-02: 62 (that reader thought reality was 45)" in text
    assert "reality was" not in describe(pulse, log, blind=True)
