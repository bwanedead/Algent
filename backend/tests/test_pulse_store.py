"""Ohmega Pulse: the store defends the ledger, and state is a replay of it."""

from __future__ import annotations

import pytest

from algent_backend.agent_system.agents.pulse import (
    Anchor,
    Confidence,
    DuplicateInfluence,
    Influence,
    Pulse,
    PulseDefinition,
    PulseStore,
    Situation,
    Source,
    Watch,
)


def _store(tmp_path) -> PulseStore:
    store = PulseStore(tmp_path / "pulse_store")
    store.save_situation(Situation(id="sit_rn", title="Russia–NATO"))
    store.create_pulse(Pulse(
        id="pls_rn_mil", situation_id="sit_rn", name="Military confrontation",
        definitions=[PulseDefinition(question="How close are Russia and NATO to direct fighting?",
                                     anchors=[Anchor(position=0, meaning="routine"),
                                              Anchor(position=100, meaning="direct war")])]))
    return store


def _inf(at: str, pos, *, mode="article", decision="applied", run="r1", event="e1", v=1,
         conf=None) -> Influence:
    return Influence(pulse_id="pls_rn_mil", at=at, evidence_through=at[:10], mode=mode,
                     definition_version=v, proposed_position=pos, decision=decision,
                     rationale="because", confidence=conf or Confidence(),
                     source=Source(run_id=run, event_id=event))


def test_a_pulse_joins_its_situation_and_has_versioned_definitions(tmp_path) -> None:
    store = _store(tmp_path)
    assert store.situation("sit_rn").pulse_ids == ["pls_rn_mil"]
    v2 = store.add_definition("pls_rn_mil", PulseDefinition(question="sharper", note="clearer anchors"))
    pulse = store.pulse("pls_rn_mil")
    assert v2 == 2 and [d.version for d in pulse.definitions] == [1, 2]
    assert pulse.definitions[0].question.startswith("How close")     # v1 kept, never edited


def test_the_same_assessment_act_cannot_be_written_twice(tmp_path) -> None:
    store = _store(tmp_path)
    store.append(_inf("2026-09-01T00:00:00+00:00", 40, mode="seed", run="seed"))
    with pytest.raises(DuplicateInfluence):
        store.append(_inf("2026-09-01T00:05:00+00:00", 45, mode="seed", run="seed"))  # a retry
    assert len(store.log("pls_rn_mil")) == 1


def test_off_ruler_positions_and_unknown_rulers_are_refused(tmp_path) -> None:
    store = _store(tmp_path)
    with pytest.raises(ValueError):
        store.append(_inf("2026-09-01T00:00:00+00:00", 140))
    with pytest.raises(ValueError):
        store.append(_inf("2026-09-01T00:00:00+00:00", 40, v=7))


def test_state_is_the_latest_applied_position_not_a_sum_of_deltas(tmp_path) -> None:
    store = _store(tmp_path)
    store.append(_inf("2026-08-01T00:00:00+00:00", 40, mode="seed", run="seed", event="-"))
    store.append(_inf("2026-08-20T00:00:00+00:00", 45, event="e1"))
    store.append(_inf("2026-09-01T00:00:00+00:00", None, decision="no_change", event="e2"))
    store.append(_inf("2026-09-10T00:00:00+00:00", 58, event="e3",
                      conf=Confidence(evidence_quality="high", coverage="high", agreement="high")))
    s = store.state("pls_rn_mil")
    assert s.position == 58 and s.band == "severe" and s.confidence == "high"
    assert [p.position for p in s.history] == [40, 45, 58]
    assert [p.band for p in s.band_changes] == ["elevated", "severe"]   # 45 stayed elevated
    assert s.velocity_7d == 13 and s.velocity_30d == 18                # vs Sep 3 (45), Aug 11 (40)
    assert s.influences == 4                                          # no_change is still logged
    assert s.last_assessed.startswith("2026-09-10")


def test_the_past_is_a_replay_with_a_cutoff(tmp_path) -> None:
    store = _store(tmp_path)
    store.append(_inf("2026-08-01T00:00:00+00:00", 40, mode="seed", run="seed", event="-"))
    store.append(_inf("2026-09-10T00:00:00+00:00", 58, event="e3"))
    assert store.state("pls_rn_mil", as_of="2026-08-15T00:00:00+00:00").position == 40


def test_a_blind_read_never_moves_the_pulse_but_a_wide_gap_flags_it(tmp_path) -> None:
    store = _store(tmp_path)
    store.append(_inf("2026-09-01T00:00:00+00:00", 70, mode="seed", run="seed", event="-"))
    store.append(_inf("2026-09-08T00:00:00+00:00", 40, mode="blind", run="w1", event="-"))
    s = store.state("pls_rn_mil")
    assert s.position == 70 and s.anchoring_gap == 30 and s.needs_reconciliation
    # a full reassessment — even one that holds the position — is the reconciliation
    store.append(_inf("2026-09-09T00:00:00+00:00", None, mode="reassess", decision="no_change",
                      run="w1", event="-"))
    assert not store.state("pls_rn_mil").needs_reconciliation


def test_a_resolved_watch_stays_resolved(tmp_path) -> None:
    store = _store(tmp_path)
    store.save_watch(Watch(id="w1", situation_id="sit_rn", condition="Permanent basing in Belarus",
                           pulse_ids=["pls_rn_mil"], expected_direction="up"))
    done = store.resolve_watch("w1", "triggered", by=Source(run_id="r9", article_slug="x"))
    assert done.status == "triggered" and done.resolved_by.run_id == "r9"
    with pytest.raises(ValueError):
        store.resolve_watch("w1", "expired")
    with pytest.raises(ValueError):
        store.save_watch(Watch(id="w1", situation_id="sit_rn", condition="overwrite attempt"))
