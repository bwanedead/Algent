"""Seeding: the model's proposal is checked, not trusted — and commit stores exactly what was reviewed."""

from __future__ import annotations

from algent_backend.agent_system.agents.pulse import PulseStore
from algent_backend.agent_system.agents.pulse import seed as sd
from algent_backend.agent_system.agents.pulse.catalog import SEED_SITUATIONS
from algent_backend.agent_system.agents.pulse.contracts import Anchor

SIT = SEED_SITUATIONS[0]
RULER = [Anchor(position=p, meaning=f"level {p}") for p in (0, 25, 50, 75, 100)]


def _draft(**pulse) -> sd.SituationDraft:
    base = dict(slug="Military Confrontation!", name="Military confrontation", question="How close?",
                anchors=RULER, position=62, claim_ids=["clm_a"], rationale="between 50 and 75")
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


def test_a_pulse_without_a_full_ruler_is_dropped() -> None:
    s = sd.check(SIT, _draft(anchors=RULER[:3]), {"clm_a"}, [])
    assert s.draft.pulses == [] and any("anchors at" in x for x in s.problems)


def test_commit_stores_the_reviewed_proposal_as_seed_influences(tmp_path) -> None:
    store = PulseStore(tmp_path / "ps")
    seeded = [sd.check(SIT, _draft(), {"clm_a"}, ["prof_1"])]
    assert sd.commit(store, seeded, run_id="seed_test") == 1
    pid = sd.pulse_id(SIT, "military_confrontation")
    st = store.state(pid)
    assert st.position == 62 and st.band == "severe"
    log = store.log(pid)
    assert log[0].mode == "seed" and log[0].source.claim_ids == ["clm_a"]
    w = store.watches(SIT.id)[0]
    assert w.origin_positions == {pid: 62} and w.expected_direction == "up"


def test_an_anchor_drawn_from_the_evidence_window_is_flagged() -> None:
    ruler = [Anchor(position=p, meaning="m", example=("July 2026 strikes" if p == 75 else "1987 Tanker War"))
             for p in (0, 25, 50, 75, 100)]
    s = sd.check(SIT, _draft(anchors=ruler, evidence_through="2026-09-20"), {"clm_a"}, [])
    assert any("evidence window" in x and "75" in x for x in s.problems)
