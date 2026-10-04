"""The Pulse registry: catalog, proposals that recur, dedup, promotion. Fake models only."""

from __future__ import annotations

import json

import pytest

from algent_backend.agent_system.agents.pulse import PulseStore, registry
from algent_backend.agent_system.agents.pulse.contracts import Influence, Pulse, PulseDefinition, Situation
from algent_backend.agent_system.agents.pulse.registry import Placement, ProposalRejected, Verdict

Q = "How stressed is shipping insurance?"


class _Model:
    def __init__(self, answers, calls):
        self.answers, self.calls, self.schema = answers, calls, None

    def with_structured_output(self, schema):
        self.schema = schema
        return self

    def invoke(self, messages, **_k):
        self.calls.append((self.schema, messages[1].content))
        return self.answers[self.schema]


def _ctx(*, duplicate_of=None, situation_id=None, calls=None):
    model = _Model({Verdict: Verdict(duplicate_of=duplicate_of, reason="r"),
                    Placement: Placement(situation_id=situation_id, reason="r")}, [] if calls is None else calls)
    return type("X", (), {"model_resolver": type("R", (), {
        "resolve": lambda _s, _spec: type("C", (), {"client": model})()})()})()


def _store(tmp_path) -> PulseStore:
    store = PulseStore(tmp_path / "ps")
    store.save_situation(Situation(id="sit_gulf", title="Iran and the Gulf", summary="s"))
    store.save_situation(Situation(id="sit_old", title="Old", status="merged"))
    store.create_pulse(Pulse(id="pls_gulf_hormuz", situation_id="sit_gulf", name="Hormuz",
                             definitions=[PulseDefinition(question="How closed is Hormuz?", low_end="open",
                                                          high_end="shut")]))
    store.create_pulse(Pulse(id="pls_old_x", situation_id="sit_old", name="X",
                             definitions=[PulseDefinition(question="q", low_end="a", high_end="b")]))
    for at, pos in (("2026-09-20T10:00:00+00:00", 30), ("2026-09-27T10:00:00+00:00", 45)):
        store.append(Influence(pulse_id="pls_gulf_hormuz", at=at, mode="article", definition_version=1,
                               proposed_position=pos, decision="applied", rationale="r", key=f"k{at}"))
    return store


def _prop(run="r1", day="2026-09-28", theater="thr_a", **kw) -> dict:
    base = {"name": "Shipping Insurance Stress", "question": Q, "low_end": "calm", "high_end": "uninsurable",
            "why": "premiums moved", "situation_hint": "Red Sea shipping", "at": f"{day}T12:00:00+00:00",
            "source": {"kind": "daily", "run_id": run, "theater_id": theater, "domain": "geopolitics"}}
    return {**base, **kw}


def test_catalog_shape_and_filters(tmp_path) -> None:
    rows = registry.catalog(_store(tmp_path))
    assert [r["id"] for r in rows] == ["pls_gulf_hormuz"]                    # merged situation skipped
    r = rows[0]
    assert set(r) == {"id", "situation_id", "situation", "name", "question", "low_end", "high_end", "status",
                      "position", "band", "confidence", "last_assessed", "evidence_through", "velocity_7d",
                      "history"}
    assert r["situation"] == "Iran and the Gulf" and r["position"] == 45 and r["status"] == "experimental"
    assert [h["position"] for h in r["history"]] == [30, 45] and "absolute_position" not in json.dumps(rows)


def test_propose_validates() -> None:
    store = PulseStore.__new__(PulseStore)           # never reached: validation fails first
    for bad in (_prop(why=""), _prop(source={"kind": "bot", "run_id": "r"}),
                _prop(source={"kind": "daily", "run_id": ""}),
                _prop(question="How tense is it and how likely is war?"),
                _prop(question="How tense? How likely?")):
        with pytest.raises(ProposalRejected):
            registry.propose(store, bad)


def test_sightings_and_ready(tmp_path) -> None:
    store = _store(tmp_path)
    first = registry.propose(store, _prop())
    assert first["recorded"] and first["sightings"] == 1
    assert not registry.propose(store, _prop())["recorded"]                   # identical sighting not repeated
    registry.propose(store, _prop(theater="thr_b"))                           # same run, other theater: still one voice
    assert not registry.ready(store.proposals())
    registry.propose(store, _prop(run="r2", day="2026-09-28"))                # other run, same date: not enough
    assert not registry.ready(store.proposals())
    out = registry.propose(store, _prop(run="r3", day="2026-09-29"))          # other run, other date
    assert out["sightings"] == 4
    [row] = registry.ready(store.proposals())
    assert row["id"] == first["id"] and row["sightings"] == 4 and len(row["runs"]) == 3 and len(row["dates"]) == 2


def test_promote_creates_pulse_situation_and_ledger_line_but_no_position(tmp_path) -> None:
    store, calls = _store(tmp_path), []
    pid = registry.propose(store, _prop())["id"]
    out = registry.promote(_ctx(situation_id=None, calls=calls), None, store, pid, model_spec=None)
    assert out["status"] == "promoted" and out["situation_id"] == "sit_red_sea_shipping"
    sit = store.situation("sit_red_sea_shipping")
    assert sit.title == "Red Sea shipping" and sit.pulse_ids == [out["pulse_id"]]
    pulse = store.pulse(out["pulse_id"])
    assert pulse.status == "experimental" and pulse.definition.question == Q
    assert pulse.definition.note == f"promoted from proposal {pid}: premiums moved"
    assert store.log(pulse.id) == [] and store.state(pulse.id).position is None   # never invents a reading
    assert store.proposals()[-1]["kind"] == "promoted" and store.proposals()[-1]["pulse_id"] == pulse.id
    assert registry.promote(_ctx(), None, store, pid, model_spec=None)["status"] == "already_promoted"
    assert not registry.ready(store.proposals())


def test_promote_uses_the_named_or_chosen_situation(tmp_path) -> None:
    store = _store(tmp_path)
    a = registry.propose(store, _prop())["id"]
    out = registry.promote(_ctx(), None, store, a, situation_id="sit_gulf", model_spec=None)
    assert out["situation_id"] == "sit_gulf" and out["pulse_id"] == "pls_gulf_shipping_insurance_stress"
    b = registry.propose(store, _prop(name="Hormuz Traffic", question="How thin is Hormuz traffic?"))["id"]
    assert registry.promote(_ctx(situation_id="sit_gulf"), None, store, b, model_spec=None)["situation_id"] == "sit_gulf"
    c = registry.propose(store, _prop(name="Other", question="How odd is other?"))["id"]
    assert registry.promote(_ctx(), None, store, c, situation_id="sit_nope", model_spec=None)["status"] == \
        "unknown_situation"
    d = registry.propose(store, _prop(name="Lost", question="How lost is it?", situation_hint=""))["id"]
    assert registry.promote(_ctx(), None, store, d, model_spec=None)["status"] == "no_situation"


def test_duplicate_is_not_promoted(tmp_path) -> None:
    store = _store(tmp_path)
    pid = registry.propose(store, _prop(name="Hormuz Closure", question="How shut is the strait of Hormuz?"))["id"]
    out = registry.promote(_ctx(duplicate_of="pls_gulf_hormuz"), None, store, pid, model_spec=None)
    assert out["status"] == "duplicate" and out["duplicate_of"] == "pls_gulf_hormuz"
    assert [p.id for p in store.pulses()] == ["pls_gulf_hormuz", "pls_old_x"]
    assert store.proposals()[-1]["kind"] == "duplicate"
    registry.propose(store, _prop(name="Hormuz Closure", question="How shut is the strait of Hormuz?", run="r9",
                                  day="2026-10-01"))
    assert not registry.ready(store.proposals())                              # rejected stays rejected


def test_dedup_exact_question_needs_no_model_and_unknown_ids_are_ignored(tmp_path) -> None:
    store, calls = _store(tmp_path), []
    same = registry.is_duplicate(_ctx(calls=calls), None, store,
                                 _prop(question="how closed is hormuz"), None)
    assert same.duplicate_of == "pls_gulf_hormuz" and calls == []
    unknown = registry.is_duplicate(_ctx(duplicate_of="pls_made_up", calls=calls), None, store, _prop(), None)
    assert unknown.duplicate_of is None and len(calls) == 1
    assert registry.is_duplicate(_ctx(calls=calls), None, PulseStore(tmp_path / "empty"), _prop(), None).duplicate_of is None
    assert len(calls) == 1                                                    # empty catalog: no model call


def test_promote_ready_reports_and_never_raises(tmp_path) -> None:
    store = _store(tmp_path)
    registry.propose(store, _prop())
    registry.propose(store, _prop(run="r2", day="2026-09-29"))
    registry.propose(store, _prop(name="Once", question="How once is it?"))
    report = registry.promote_ready(_ctx(), None, store, model_spec=None)
    assert [p["name"] for p in report["promoted"]] == ["Shipping Insurance Stress"]
    assert report["duplicates"] == [] and report["errors"] == []
    registry.propose(store, _prop(name="B", question="How b?", run="r1"))
    registry.propose(store, _prop(name="B", question="How b?", run="r2", day="2026-09-29"))
    broken = type("X", (), {"model_resolver": None})()
    assert len(registry.promote_ready(broken, None, store, model_spec=None)["errors"]) == 1


def test_legacy_migration_is_idempotent(tmp_path) -> None:
    legacy = tmp_path / "pulse_proposals.jsonl"
    rows = [{"date": "2026-09-28", "domain": "geopolitics", "theater_id": "thr_a", "theater": "Alpha",
             "name": "Shipping Insurance Stress", "question": Q, "low_end": "calm", "high_end": "crisis", "why": "gap"},
            {"date": "2026-09-28", "name": "Broken", "question": "q"}]
    legacy.write_text("\n".join(json.dumps(r) for r in rows) + "\nnot json\n", encoding="utf-8")
    store = PulseStore(tmp_path / "ps")
    assert registry.migrate_legacy_proposals(legacy, store) == {"migrated": 1, "skipped_invalid": 2}
    assert registry.migrate_legacy_proposals(legacy, store)["migrated"] == 0
    assert len(store.proposals()) == 1 and store.proposals()[0]["situation_hint"] == "Alpha"
    assert legacy.is_file()
