"""Pulse rescue: rebuild the lost stretch of the ledger from the site's published documents and the dailies. Idempotent, never overwrites."""

from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from algent_backend.agent_system.agents.pulse import rescue
from algent_backend.agent_system.agents.pulse.contracts import Influence, Pulse, PulseDefinition, Situation
from algent_backend.agent_system.agents.pulse.store import PulseStore


def make_store(tmp_path) -> PulseStore:
    store = PulseStore(tmp_path / "ps")
    store.save_situation(Situation(id="sit_a", title="A"))
    store.create_pulse(Pulse(id="pls_a", situation_id="sit_a", name="Military confrontation", definitions=[PulseDefinition(question="q")]))
    store.append(Influence(pulse_id="pls_a", at="2026-10-05T10:00:00+00:00", mode="reassess", definition_version=1, proposed_position=40.0,
                           decision="applied", rationale="native"))
    return store


def reading(at: str, position: float, **kw) -> dict:
    return {"at": at, "mode": "reassessment", "moves_pulse": True, "decision": "applied", "position": position, "rationale": "published words",
            "confidence": "medium", "evidence_through": at[:10], "model": "m", "article_url": None, **kw}


def pulse_doc(pid: str, readings: list[dict], **kw) -> dict:
    return {"schema": "ohmega.pulse/1", "id": pid, "name": kw.pop("name", pid), "situation_id": kw.pop("situation_id", "sit_a"),
            "situation": "A", "status": "active", "definition": {"version": 1, "question": "Q?", "low_end": "calm", "high_end": "war"},
            "readings": readings, **kw}


def daily(path: Path, day: str, rows: dict[str, float]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps({"date": day, "theaters": [{"theater_id": "t", "pulses": [{"id": p, "name": p, "position": v} for p, v in rows.items()]}]}),
                    encoding="utf-8")


@pytest.fixture
def world(tmp_path):
    store = make_store(tmp_path)
    resc = tmp_path / "rescue"
    resc.mkdir()
    (resc / "pulse_pls_a.json").write_text(json.dumps(pulse_doc("pls_a", [
        reading("2026-10-05T10:00:00+00:00", 99.0),                       # already in the store (native wins, the rescue must not touch it)
        reading("2026-10-08T09:00:00+00:00", 44.0, article_url="/articles/some-slug"),
        reading("2026-10-10T08:00:00+00:00", 47.0, mode="audit", decision="no_change")])), encoding="utf-8")
    (resc / "pulse_pls_b.json").write_text(json.dumps(pulse_doc("pls_b", [reading("2026-10-09T09:00:00+00:00", 20.0)], name="Trade", situation_id="sit_b")),
                                           encoding="utf-8")
    (resc / "pulses.json").write_text("{}", encoding="utf-8")                # the list is not a pulse document: ignored
    dailies = tmp_path / "dailies"
    daily(dailies / "geopolitics" / "2026-10-09.json", "2026-10-09", {"pls_a": 46.0})        # before the last rescued reading: not reconstructed
    daily(dailies / "geopolitics" / "2026-10-12.json", "2026-10-12", {"pls_a": 50.0, "pls_b": 25.0, "pls_unknown": 5.0})
    daily(dailies / "ai" / "2026-10-13.json", "2026-10-13", {"pls_a": 52.0})
    return store, resc, dailies


def test_dry_run_reports_and_writes_nothing(world) -> None:
    store, resc, dailies = world
    rep = rescue.rebuild(store, resc, dailies, dry_run=True)
    assert rep["rescued"]["readings_added"] == 3 and rep["rescued"]["readings_present"] == 1 and rep["rescued"]["pulses_created"] == 1
    assert len(store.log("pls_a")) == 1 and store.pulse("pls_b") is None


def test_rescued_readings_keep_timestamps_and_say_where_they_came_from(world) -> None:
    store, resc, dailies = world
    rep = rescue.rebuild(store, resc, dailies)
    assert rep["rescued"] == {"pulses_seen": 2, "pulses_created": 1, "readings_added": 3, "readings_present": 1}
    log = {i.at: i for i in store.log("pls_a")}
    assert log["2026-10-05T10:00:00+00:00"].proposed_position == 40.0 and log["2026-10-05T10:00:00+00:00"].provenance == ""     # never overwritten
    got = log["2026-10-08T09:00:00+00:00"]
    assert got.provenance == rescue.RESCUED and got.proposed_position == 44.0 and got.source.article_slug == "some-slug" and got.rationale == "published words"
    assert log["2026-10-10T08:00:00+00:00"].mode == "blind" and log["2026-10-10T08:00:00+00:00"].decision == "no_change"
    b = store.pulse("pls_b")
    assert b is not None and b.definition.question == "Q?" and store.situation("sit_b") is not None and store.log("pls_b")[0].provenance == rescue.RESCUED


def test_days_after_the_last_reading_are_reconstructed_from_the_dailies_with_no_rationale(world) -> None:
    store, resc, dailies = world
    rep = rescue.rebuild(store, resc, dailies)
    assert rep["reconstructed"]["readings_added"] == 3                        # pls_a 10-12 and 10-13, pls_b 10-12; pls_unknown has no Pulse; 10-09 predates the rescue
    recon = [i for i in store.log("pls_a") if i.provenance == rescue.RECONSTRUCTED]
    assert [i.evidence_through for i in recon] == ["2026-10-12", "2026-10-13"] and [i.proposed_position for i in recon] == [50.0, 52.0]
    assert all("No assessment rationale was recorded" in i.rationale and i.confidence.overall() == "low" for i in recon)
    assert store.state("pls_a").position == 52.0                              # the projection follows the newest reading
    assert [i.provenance for i in store.log("pls_b")] == [rescue.RESCUED, rescue.RECONSTRUCTED]


def test_a_second_run_adds_nothing(world) -> None:
    store, resc, dailies = world
    rescue.rebuild(store, resc, dailies)
    before = {p: len(store.log(p)) for p in ("pls_a", "pls_b")}
    again = rescue.rebuild(store, resc, dailies)
    assert again["rescued"]["readings_added"] == 0 and again["reconstructed"]["readings_added"] == 0
    assert {p: len(store.log(p)) for p in ("pls_a", "pls_b")} == before


def test_a_day_with_a_native_reading_is_not_reconstructed(world) -> None:
    store, resc, dailies = world
    store.append(Influence(key="inf_native_later", pulse_id="pls_a", at="2026-10-13T20:00:00+00:00", mode="reassess", definition_version=1, proposed_position=61.0,
                           decision="applied", rationale="native later"))
    rescue.rebuild(store, resc, dailies)
    assert [i.evidence_through for i in store.log("pls_a") if i.provenance == rescue.RECONSTRUCTED] == ["2026-10-12"]


def test_provenance_is_visible_in_the_published_reading() -> None:
    from algent_backend.publishing.agent_feed import _reading

    native = Influence(pulse_id="p", at="2026-10-05T10:00:00+00:00", mode="reassess", definition_version=1, decision="applied", rationale="x")
    assert "provenance" not in _reading(native)
    assert _reading(native.model_copy(update={"provenance": rescue.RECONSTRUCTED}))["provenance"] == rescue.RECONSTRUCTED


def test_the_cli_verb_is_wired(world, capsys, monkeypatch) -> None:
    from algent_backend.cli.newsroom import pulse as cli
    from algent_backend.agent_system.agents.pulse import repository

    store, resc, dailies = world
    monkeypatch.setattr(repository, "pulse_store", lambda: store)

    args = SimpleNamespace(pulse_verb="rebuild", from_rescue=str(resc), dailies=str(dailies), dry_run=True)
    assert cli.run_pulse(args) == 0
    assert json.loads(capsys.readouterr().out)["rescued"]["readings_added"] == 3
