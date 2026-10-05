"""Actors publish: which actors are written, from which semantic fields, and how bounded."""

from __future__ import annotations

import pytest

from algent_backend.actors import registry, store
from algent_backend.actors.contracts import Leaders, Observation, Official
from algent_backend.agent_system.agents.statements import store as statements_store
from algent_backend.agent_system.agents.statements.contracts import Statement
from algent_backend.publishing import actors_feed

AT = "2026-10-04T00:00:00+00:00"


@pytest.fixture(autouse=True)
def _stores(tmp_path, monkeypatch):
    monkeypatch.setenv("ALGENT_ACTORS_STORE", str(tmp_path / "a"))
    monkeypatch.setenv("ALGENT_STATEMENTS_STORE", str(tmp_path / "s"))


def _fill(isos):
    store.append("population", [Observation(iso2=i, indicator="population", year=2025, value=1e6 * (n + 1), source="wb",
                                            source_url="u", fetched_at=AT) for n, i in enumerate(isos)])
    store.append_leaders([Leaders(iso2="RU", head_of_state=Official(name="Vladimir Putin"), fetched_at=AT, source_url="s")])


DOSSIERS = {"theaters": {"t1": {
    "name": "Black Sea", "actors": [{"name": "Russia", "mentions": 5}, {"name": "Ukraine", "mentions": 3},
                                    {"name": "Russian Black Sea Fleet", "mentions": 9}],
    "relations": [{"source": "Russia", "target": "Moldova", "count": 2}],
    "places": [{"name": "Odesa", "country": "Ukraine", "count": 1}],
    "pulses": [{"id": "p1", "name": "Black Sea shipping", "band": "severe", "position": 71.0}]}}}


def test_rule_resolves_names_never_prose() -> None:
    inv = actors_feed._involvement(DOSSIERS["theaters"])
    assert set(inv) == {"RU", "UA", "MD"}                                  # the fleet is not a country name: ignored
    assert inv["RU"]["theaters"] == [{"id": "t1", "name": "Black Sea", "mentions": 7}]
    assert inv["UA"]["pulses"][0]["id"] == "p1"


def test_published_set_is_standing_plus_named_and_bounded(monkeypatch) -> None:
    assert {"US", "RU", "CN", "GB", "FR", "DE", "SA"} <= set(actors_feed.select({}, {}))      # G20 + P5 always
    sel = actors_feed.select(DOSSIERS["theaters"], {})
    assert "UA" in sel and "MD" in sel and len(sel) == len(set(sel))
    monkeypatch.setattr(actors_feed, "MAX_REFERENCED", 1)
    extra = [i for i in actors_feed.select(DOSSIERS["theaters"], {}) if i not in registry.G20 and i not in registry.UNSC_P5]
    assert extra == ["UA"] or len(extra) == 1                                # RU is standing; the bound keeps the most involved


def test_actor_files_carry_profile_statements_involvement_and_credits() -> None:
    _fill(["RU", "UA", "US"])
    statements_store.append_statements([Statement(
        id="st_1", speaker="Vladimir Putin", role="President", affiliation="Russia", date="2026-10-01",
        quote="We will respond", signal="warning", stance=-1, source_url="http://kremlin.example/x", transcript_id="t")])
    files = actors_feed.build_actor_files(DOSSIERS)
    assert files["index.json"]["schema"] == "ohmega.actor.index/1"
    ru = files["RU.json"]
    assert ru["schema"] == "ohmega.actor/1" and ru["url"] == "/intel/actors/RU" and ru["data_as_of"] == "2026-10-04"
    assert ru["statements"][0]["text"] == "We will respond" and ru["statements"][0]["is_quote"]
    assert ru["involved"]["theaters"][0]["id"] == "t1" and ru["involved"]["pulses"][0]["band"] == "severe"
    assert {c["source"] for c in ru["credits"]} >= {"wb", "wikidata", "nuclear"}
    assert "MD" not in files and "UA.json" in files                         # nothing stored for Moldova: no empty page
    row = next(r for r in files["index.json"]["actors"] if r["iso2"] == "RU")
    assert row["population"]["value"] == 1e6 and row["theaters"] == 1 and row["statements"] == 1
    assert actors_feed.build_actor_files(DOSSIERS) == files                 # byte-stable on an unchanged store


def test_empty_store_publishes_nothing() -> None:
    assert actors_feed.build_actor_files(DOSSIERS) == {}
