"""Weekly reassessment: anchored then blind; the blind read audits, never moves; one run a week."""

from __future__ import annotations

from algent_backend.agent_system.agents.pulse import (
    Anchor,
    Influence,
    Pulse,
    PulseDefinition,
    PulseStore,
    Situation,
    Source,
)
from algent_backend.agent_system.agents.pulse import reassess as ra

PROFILES = {"prof_1": {"id": "prof_1", "title": "t", "claim_ledger": [
    {"id": "clm_a", "status": "confirmed", "salience": "high", "text": "Talks resumed."}]}}


class _Seq:
    """Returns the anchored reading, then the blind one, in call order."""

    def __init__(self, *outs):
        self.outs = list(outs)

    def with_structured_output(self, _schema):
        return self

    def invoke(self, *_a, **_k):
        return self.outs.pop(0)


def _ctx(model):
    return type("X", (), {"model_resolver": type("R", (), {
        "resolve": lambda _s, _spec: type("C", (), {"client": model})()})()})()


def _store(tmp_path) -> tuple[PulseStore, Pulse]:
    store = PulseStore(tmp_path / "ps")
    store.save_situation(Situation(id="sit_x", title="X"))
    pulse = Pulse(id="pls_x", situation_id="sit_x", name="Tension", definitions=[
        PulseDefinition(question="q", anchors=[Anchor(position=p, meaning=str(p)) for p in (0, 25, 50, 75, 100)])])
    store.create_pulse(pulse)
    store.append(Influence(pulse_id="pls_x", at="2026-09-01T00:00:00+00:00", mode="seed",
                           definition_version=1, proposed_position=70, decision="applied", rationale="seed",
                           source=Source(run_id="seed", claim_ids=["clm_a"])))
    return store, store.pulse("pls_x")


def test_anchored_moves_blind_audits_and_a_wide_gap_is_flagged(tmp_path) -> None:
    store, pulse = _store(tmp_path)
    model = _Seq(ra.Reassessment(position=60, claim_ids=["clm_a"], rationale="cooled"),
                 ra.Reading(position=30, claim_ids=["clm_a"], rationale="evidence alone says calmer"))
    report = ra.reassess_pulse(_ctx(model), None, store, pulse, PROFILES, model_spec=None, run_id="reassess_w1")
    assert report["before"] == 70 and report["after"] == 60          # anchored applied; blind did not
    assert report["anchoring_gap"] == 30 and report["needs_reconciliation"]


def test_the_same_week_cannot_reassess_twice(tmp_path) -> None:
    store, pulse = _store(tmp_path)
    outs = [ra.Reassessment(position=65, claim_ids=["clm_a"]), ra.Reading(position=64, claim_ids=["clm_a"])]
    ra.reassess_pulse(_ctx(_Seq(*outs)), None, store, pulse, PROFILES, model_spec=None, run_id="reassess_w1")
    again = ra.reassess_pulse(_ctx(_Seq(ra.Reassessment(position=20, claim_ids=["clm_a"]),
                                        ra.Reading(position=20, claim_ids=["clm_a"]))),
                              None, store, pulse, PROFILES, model_spec=None, run_id="reassess_w1")
    assert again["anchored"] == {"refused": "DuplicateInfluence"}
    assert store.state("pls_x").position == 65


def test_no_evidence_means_no_reassessment(tmp_path) -> None:
    store, pulse = _store(tmp_path)
    report = ra.reassess_pulse(_ctx(_Seq()), None, store, pulse, {}, model_spec=None, run_id="w")
    assert report == {"pulse": "pls_x", "skipped": "no evidence yet"}
