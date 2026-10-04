"""Freshness: radar headlines make a situation stale; they never move a Pulse."""

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
from algent_backend.agent_system.agents.pulse import freshness as fr
from algent_backend.agent_system.agents.pulse.seed import AttachLink, AttachPlan

PORTFOLIO = {"vectors": [{"id": "v01", "title": "Drones over Poland", "thesis": "jets scrambled"},
                         {"id": "v02", "title": "Sushi wars", "thesis": "chains"}]}


class _Attach:
    def with_structured_output(self, _s):
        return self

    def invoke(self, *_a, **_k):
        return AttachPlan(links=[AttachLink(situation_id="sit_rn", profile_ids=["v01"])])


CTX = type("X", (), {"model_resolver": type("R", (), {
    "resolve": lambda _s, _spec: type("C", (), {"client": _Attach()})()})()})()


def _store(tmp_path) -> PulseStore:
    store = PulseStore(tmp_path / "ps")
    store.save_situation(Situation(id="sit_rn", title="Russia–NATO", summary="friction"))
    store.create_pulse(Pulse(id="pls_rn", situation_id="sit_rn", name="m", definitions=[
        PulseDefinition(question="q", anchors=[Anchor(position=p, meaning="-") for p in (0, 25, 50, 75, 100)])]))
    store.append(Influence(pulse_id="pls_rn", at="2026-09-01T00:00:00+00:00", mode="seed",
                           definition_version=1, proposed_position=50, decision="applied",
                           rationale="seed", source=Source(run_id="seed")))
    return store


def test_headlines_since_the_last_assessment_are_unprocessed_and_move_nothing(tmp_path) -> None:
    store = _store(tmp_path)
    assert fr.record_radar(CTX, None, store, PORTFOLIO, attach_spec=None, edition="2026-09-30-1200") == {"sit_rn": 1}
    assert fr.record_radar(CTX, None, store, PORTFOLIO, attach_spec=None, edition="2026-09-30-1200") == {}  # same edition
    assert [r["headline"] for r in fr.unprocessed(store, "sit_rn")] == ["Drones over Poland"]
    assert store.state("pls_rn").position == 50 and len(store.log("pls_rn")) == 1   # never moved

    # researched evidence arrives: the backlog counts as processed
    store.append(Influence(pulse_id="pls_rn", at="2099-01-01T00:00:00+00:00", mode="article",
                           definition_version=1, decision="no_change", rationale="read it",
                           source=Source(run_id="r2")))
    assert fr.unprocessed(store, "sit_rn") == []
