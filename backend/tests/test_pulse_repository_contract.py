"""
One contract, every store: the file store and the Postgres store must behave identically.

The Postgres variant runs only when ALGENT_TEST_DATABASE_URL is set and psycopg is installed, and
then inside a throwaway schema created from migrations/001 and dropped afterwards — never against
the live Pulse data.
"""

from __future__ import annotations

import importlib.util
import os
import uuid
from pathlib import Path

import pytest

from algent_backend.agent_system.agents.pulse import (
    Anchor,
    DuplicateInfluence,
    Event,
    Influence,
    Pulse,
    PulseDefinition,
    PulseStore,
    Situation,
    Source,
    Watch,
)

_PG = os.environ.get("ALGENT_TEST_DATABASE_URL", "")
_PG_OK = bool(_PG) and importlib.util.find_spec("psycopg") is not None


@pytest.fixture(params=["files", pytest.param("postgres", marks=pytest.mark.skipif(
    not _PG_OK, reason="set ALGENT_TEST_DATABASE_URL (+ psycopg) to run against Postgres"))])
def store(request, tmp_path):
    if request.param == "files":
        yield PulseStore(tmp_path / "ps")
        return
    import psycopg

    from algent_backend.agent_system.agents.pulse.pg_store import PgPulseStore

    schema = f"pulse_test_{uuid.uuid4().hex[:8]}"
    conn = psycopg.connect(_PG)
    with conn.transaction():
        conn.execute(f"create schema {schema}")
        conn.execute(f"set search_path to {schema}")
        conn.execute((Path(__file__).resolve().parents[1] / "migrations" / "001_pulse.sql").read_text(encoding="utf-8"))
    try:
        yield PgPulseStore(conn)
    finally:
        with conn.transaction():
            conn.execute(f"drop schema {schema} cascade")
        conn.close()


def _seed(store) -> None:
    store.save_situation(Situation(id="sit_a", title="A", summary="s"))
    store.create_pulse(Pulse(id="pls_a", situation_id="sit_a", name="n", definitions=[
        PulseDefinition(question="q", anchors=[Anchor(position=p, meaning=str(p)) for p in (0, 25, 50, 75, 100)])]))


def _inf(at, pos, *, run="r1", mode="article", decision="applied"):
    return Influence(pulse_id="pls_a", at=at, evidence_through=at[:10], mode=mode, definition_version=1,
                     proposed_position=pos, decision=decision, rationale="x", source=Source(run_id=run))


def test_situation_and_versioned_pulse(store) -> None:
    _seed(store)
    assert store.situation("sit_a").pulse_ids == ["pls_a"]
    assert store.add_definition("pls_a", PulseDefinition(question="q2")) == 2
    assert [d.version for d in store.pulse("pls_a").definitions] == [1, 2]


def test_ledger_is_idempotent_and_projects_position(store) -> None:
    _seed(store)
    store.append(_inf("2026-09-01T00:00:00+00:00", 40, run="seed", mode="seed"))
    store.append(_inf("2026-09-10T00:00:00+00:00", 58))
    with pytest.raises(DuplicateInfluence):
        store.append(_inf("2026-09-11T00:00:00+00:00", 90))            # same run + mode + event
    st = store.state("pls_a")
    assert st.position == 58 and st.band == "severe" and len(store.log("pls_a")) == 2


def test_events_merge_sightings_and_watches_resolve_once(store) -> None:
    _seed(store)
    store.record_event(Event(id="evt_1", summary="x", situation_ids=["sit_a"], sources=[Source(run_id="r1")]))
    ev = store.record_event(Event(id="evt_1", summary="x", situation_ids=["sit_a"], sources=[Source(run_id="r2")]))
    assert len(ev.sources) == 2
    rows = [{"key": "e1:v1", "at": "2026-09-30T00:00:00+00:00", "edition": "e1", "headline": "h"}]
    assert store.add_sightings("sit_a", rows) == 1 and store.add_sightings("sit_a", rows) == 0
    store.save_watch(Watch(id="w1", situation_id="sit_a", condition="c", pulse_ids=["pls_a"]))
    assert store.resolve_watch("w1", "triggered").status == "triggered"
    with pytest.raises(ValueError):
        store.resolve_watch("w1", "expired")
    assert store.watches("sit_a")[0].pulse_ids == ["pls_a"]
