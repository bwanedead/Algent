"""Seeding: the model's proposal is checked, not trusted — and commit stores exactly what was reviewed."""

from __future__ import annotations

from algent_backend.agent_system.agents.pulse import PulseStore
from algent_backend.agent_system.agents.pulse import seed as sd
from algent_backend.agent_system.agents.pulse.catalog import SEED_SITUATIONS
from algent_backend.agent_system.agents.pulse.framing import describe

SIT = SEED_SITUATIONS[0]
FRAME = dict(low_end="routine, professional contact", high_end="open war between them")


def _draft(**pulse) -> sd.SituationDraft:
    base = dict(slug="Military Confrontation!", name="Military confrontation", question="How close?",
                position=62, claim_ids=["clm_a"], rationale="more than routine, far from war", **FRAME)
    return sd.SituationDraft(summary="s", pulses=[sd.PulseDraft(**{**base, **pulse})],
                             watches=[sd.WatchDraft(condition="basing in Belarus",
                                                    pulse_slugs=["military_confrontation"],
                                                    expected_direction="up"),
                                      sd.WatchDraft(condition="orphan", pulse_slugs=["nope"])])


def test_a_grounded_position_survives_and_the_slug_is_cleaned() -> None:
    s = sd.check(SIT, _draft(), {"clm_a"}, ["prof_1"])
    p = s.draft.pulses[0]
    assert p.slug == "military_confrontation" and p.position == 62 and p.claim_ids == ["clm_a"]
    assert [w.condition for w in s.draft.watches] == ["basing in Belarus"]   # orphan watch dropped


def test_an_ungrounded_position_becomes_unassessed() -> None:
    s = sd.check(SIT, _draft(claim_ids=["clm_invented"]), {"clm_a"}, [])
    assert s.draft.pulses[0].position is None
    assert any("not in the evidence" in x for x in s.problems)
    assert any("left unassessed" in x for x in s.problems)


def test_a_pulse_without_its_calm_and_extreme_ends_is_dropped() -> None:
    s = sd.check(SIT, _draft(high_end=""), {"clm_a"}, [])
    assert s.draft.pulses == [] and any("frame" in x for x in s.problems)


def test_ids_cited_only_in_the_rationale_are_recovered_if_real() -> None:
    s = sd.check(SIT, _draft(claim_ids=[], rationale="(clm_aaaaaaaa) and (clm_ffffffff)"), {"clm_aaaaaaaa"}, [])
    p = s.draft.pulses[0]
    assert p.position == 62 and p.claim_ids == ["clm_aaaaaaaa"]      # the invented one is not recovered


def test_commit_stores_the_frame_and_the_first_reading(tmp_path) -> None:
    store = PulseStore(tmp_path / "ps")
    assert sd.commit(store, [sd.check(SIT, _draft(), {"clm_a"}, ["prof_1"])], run_id="seed_test") == 1
    pid = sd.pulse_id(SIT, "military_confrontation")
    d = store.pulse(pid).definition
    assert d.low_end.startswith("routine") and d.high_end == "open war between them" and d.anchors == []
    assert store.state(pid).position == 62
    assert store.log(pid)[0].source.claim_ids == ["clm_a"]
    assert store.watches(SIT.id)[0].origin_positions == {pid: 62}


def test_history_is_the_scale_and_the_blind_read_never_sees_it(tmp_path) -> None:
    store = PulseStore(tmp_path / "ps")
    sd.commit(store, [sd.check(SIT, _draft(), {"clm_a"}, ["prof_1"])], run_id="seed_test")
    pulse = store.pulse(sd.pulse_id(SIT, "military_confrontation"))
    seen = describe(pulse, store.log(pulse.id))
    assert "PAST READINGS" in seen and "62 — more than routine" in seen
    blind = describe(pulse, store.log(pulse.id), blind=True)
    assert "PAST READINGS" not in blind and "62" not in blind and "open war" in blind
