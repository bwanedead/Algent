"""Article update: research re-estimates the Pulses it touches — checked, logged, idempotent."""

from __future__ import annotations

from algent_backend.agent_system.agents.pulse import (
    Anchor,
    Influence,
    Pulse,
    PulseDefinition,
    PulseStore,
    Situation,
    Source,
    Watch,
)
from algent_backend.agent_system.agents.pulse import update as up
from algent_backend.agent_system.agents.pulse.seed import AttachLink, AttachPlan

PROFILE = {"id": "prof_1", "title": "Drones over Poland", "as_of": "2026-09-28",
           "claim_ledger": [{"id": "clm_ok", "status": "confirmed", "salience": "high",
                             "text": "Poland scrambled jets after Russian drones crossed."}]}


class _Model:
    def __init__(self, plan):
        self.plan = plan

    def with_structured_output(self, schema):
        self.schema = schema
        return self

    def invoke(self, *_a, **_k):
        return AttachPlan(links=[AttachLink(situation_id="sit_rn", profile_ids=["prof_1"])]) \
            if self.schema is AttachPlan else self.plan


class _Ctx:
    def __init__(self, plan):
        m = _Model(plan)
        self.model_resolver = type("R", (), {"resolve": lambda _s, _spec: type("C", (), {"client": m})()})()


def _store(tmp_path) -> PulseStore:
    store = PulseStore(tmp_path / "ps")
    store.save_situation(Situation(id="sit_rn", title="Russia–NATO", summary="friction"))
    store.create_pulse(Pulse(id="pls_rn_mil", situation_id="sit_rn", name="Military",
                             definitions=[PulseDefinition(question="q", anchors=[
                                 Anchor(position=p, meaning=str(p)) for p in (0, 25, 50, 75, 100)])]))
    store.append(Influence(pulse_id="pls_rn_mil", at="2026-09-01T00:00:00+00:00", mode="seed",
                           definition_version=1, proposed_position=55, decision="applied",
                           rationale="seed", source=Source(run_id="seed")))
    store.save_watch(Watch(id="wch_1", situation_id="sit_rn", condition="jets scrambled",
                           pulse_ids=["pls_rn_mil"]))
    return store


def _run(store, plan, run="r1"):
    return up.update_from_profile(_Ctx(plan), None, store, PROFILE, run_id=run, article_slug="a",
                                  model_spec=None, attach_spec=None)


def test_a_grounded_move_applies_and_the_event_and_watch_are_recorded(tmp_path) -> None:
    store = _store(tmp_path)
    plan = up.UpdatePlan(
        event=up.EventDraft(summary="Russian drones enter Polish airspace", occurred_on="2026-09-27"),
        updates=[up.PulseUpdate(pulse_id="pls_rn_mil", decision="applied", position=62,
                                claim_ids=["clm_ok"], rationale="closer to 75")],
        watches_triggered=[up.WatchHit(watch_id="wch_1", claim_id="clm_ok")])
    report = _run(store, plan)
    assert report["touched"] == ["sit_rn"] and store.state("pls_rn_mil").position == 62
    assert store.watches("sit_rn")[0].status == "triggered"
    inf = store.log("pls_rn_mil")[-1]
    assert inf.source.event_id.startswith("evt_") and store.event(inf.source.event_id) is not None


def test_a_move_without_valid_evidence_is_logged_as_no_change(tmp_path) -> None:
    store = _store(tmp_path)
    plan = up.UpdatePlan(updates=[
        up.PulseUpdate(pulse_id="pls_rn_mil", decision="applied", position=90, claim_ids=["clm_made_up"]),
        up.PulseUpdate(pulse_id="pls_ghost", decision="applied", position=10, claim_ids=["clm_ok"])],
        watches_triggered=[up.WatchHit(watch_id="wch_1", claim_id="clm_made_up")])
    report = _run(store, plan)
    assert store.state("pls_rn_mil").position == 55                  # not moved
    assert store.log("pls_rn_mil")[-1].decision == "no_change"        # but considered, and logged
    assert store.watches("sit_rn")[0].status == "open"                 # unproven hit ignored
    assert any("pls_ghost" in p for p in report["problems"])


def test_a_retried_run_does_not_write_history_twice(tmp_path) -> None:
    store = _store(tmp_path)
    plan = up.UpdatePlan(updates=[up.PulseUpdate(pulse_id="pls_rn_mil", decision="no_change")])
    _run(store, plan, run="r1")
    report = _run(store, plan, run="r1")
    assert len(store.log("pls_rn_mil")) == 2                           # seed + one update
    assert any("DuplicateInfluence" in p for p in report["problems"])


def test_update_quietly_never_raises(monkeypatch) -> None:
    monkeypatch.setattr(up, "update_from_profile", lambda *a, **k: 1 / 0)
    assert "error" in up.update_quietly(PROFILE, run_id="r")
