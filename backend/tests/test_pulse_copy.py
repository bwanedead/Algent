"""Copying the Pulse ledger between repositories loses nothing and can be repeated safely."""

from __future__ import annotations

from algent_backend.agent_system.agents.pulse import (
    Event,
    Influence,
    Pulse,
    PulseDefinition,
    PulseStore,
    Situation,
    Source,
    Watch,
)
from algent_backend.database.pulse_copy import copy_ledger


def test_everything_moves_and_a_second_copy_adds_nothing(tmp_path) -> None:
    src, dst = PulseStore(tmp_path / "a"), PulseStore(tmp_path / "b")
    src.save_situation(Situation(id="sit_x", title="X"))
    src.create_pulse(Pulse(id="pls_x", situation_id="sit_x", name="n",
                           definitions=[PulseDefinition(question="q", low_end="calm", high_end="war")]))
    src.add_definition("pls_x", PulseDefinition(question="q2", low_end="calm", high_end="war"))
    src.record_event(Event(id="evt_1", summary="s", situation_ids=["sit_x"]))
    for i, pos in enumerate((40, 55)):
        src.append(Influence(pulse_id="pls_x", at=f"2026-09-0{i + 1}T00:00:00+00:00", mode="article",
                             definition_version=1, proposed_position=pos, decision="applied", rationale="r",
                             source=Source(run_id=f"r{i}", event_id="evt_1")))
    src.save_watch(Watch(id="w1", situation_id="sit_x", condition="c", pulse_ids=["pls_x"]))
    src.resolve_watch("w1", "triggered", by=Source(run_id="r1"))
    src.add_sightings("sit_x", [{"key": "e:1", "at": "2026-09-02T00:00:00+00:00", "edition": "e", "headline": "h"}])

    first = copy_ledger(src, dst)
    assert first == {"situations": 1, "pulses": 1, "influences": 2, "watches": 1, "sightings": 1, "events": 1}
    assert dst.state("pls_x").position == 55 and [d.version for d in dst.pulse("pls_x").definitions] == [1, 2]
    assert [i.key for i in dst.log("pls_x")] == [i.key for i in src.log("pls_x")]   # keys preserved
    assert dst.watches()[0].status == "triggered"

    again = copy_ledger(src, dst)
    assert again["influences"] == 0 and again["pulses"] == 0 and again["watches"] == 0
