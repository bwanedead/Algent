"""Actors: append-only store, profile grouping and ranks, compare, evidence block."""

from __future__ import annotations

import pytest

from algent_backend.actors import evidence_block, compare, profile, store
from algent_backend.actors.contracts import Leaders, Observation, Official

AT = "2026-10-04T00:00:00+00:00"


@pytest.fixture(autouse=True)
def _store(tmp_path, monkeypatch):
    monkeypatch.setenv("ALGENT_ACTORS_STORE", str(tmp_path / "astore"))


def ob(ind, iso, year, value, source="wb"):
    return Observation(iso2=iso, indicator=ind, year=year, value=value, source=source, source_url="u", fetched_at=AT)


def seed():
    store.append("population", [ob("population", "RU", 2025, 143e6), ob("population", "UA", 2025, 38e6),
                                ob("population", "DE", 2025, 84e6), ob("population", "PR", 2025, 3e6)])
    store.append("gdp", [ob("gdp", "RU", 2025, 2.5e12), ob("gdp", "DE", 2025, 4.7e12)])
    store.append("gdp_pc", [ob("gdp_pc", "RU", 2025, 17500.0)])
    store.append("oil_prod", [ob("oil_prod", "RU", 2024, 6000.0, "owid")])
    store.append("gas_prod", [ob("gas_prod", "RU", 2024, 6000.0, "owid")])
    store.append("gas_cons", [ob("gas_cons", "RU", 2024, 4000.0, "owid")])
    store.append("oil_cons", [ob("oil_cons", "DE", 2024, 900.0, "owid"), ob("oil_cons", "RU", 2024, 2000.0, "owid")])
    store.append("oil_prod", [ob("oil_prod", "DE", 2024, 30.0, "owid")])
    store.append("milex", [ob("milex", "RU", 2024, 149e9)])
    store.append("milex_pct", [ob("milex_pct", "RU", 2024, 7.1)])
    store.append_leaders([Leaders(iso2="RU", head_of_state=Official(name="Vladimir Putin"),
                                  head_of_government=Official(name="Mikhail Mishustin"), fetched_at=AT, source_url="s")])


def test_append_only_new_unchanged_revised() -> None:
    r1 = store.append("gdp", [ob("gdp", "RU", 2025, 1.0), ob("gdp", "RU", 2024, 2.0)])
    assert (r1.new, r1.revised, r1.unchanged) == (2, 0, 0)
    r2 = store.append("gdp", [ob("gdp", "RU", 2025, 1.0), ob("gdp", "RU", 2024, 2.5), ob("gdp", "US", 2025, 9.0)])
    assert (r2.new, r2.revised, r2.unchanged) == (1, 1, 1)
    assert len(store.log("gdp")) == 4 and [o.revised for o in store.log("gdp")][2:] == [True, False]
    assert {(o.iso2, o.year): o.value for o in store.history("gdp")}[("RU", 2024)] == 2.5
    assert store.latest("gdp")["RU"].year == 2025
    size = store._obs_path("gdp").stat().st_size
    store.append("gdp", [ob("gdp", "RU", 2025, 1.0)])
    assert store._obs_path("gdp").stat().st_size == size


def test_leaders_append_on_change_only() -> None:
    row = Leaders(iso2="RU", head_of_state=Official(name="A", id="Q1"), fetched_at=AT, source_url="s")
    assert store.append_leaders([row]).new == 1
    assert store.append_leaders([row.model_copy(update={"fetched_at": "2026-10-05T00:00:00+00:00"})]).new == 0
    assert len(store.leaders_log()) == 1
    changed = row.model_copy(update={"head_of_state": Official(name="B", id="Q2")})
    assert store.append_leaders([changed]).revised == 1 and len(store.leaders_log()) == 2
    assert store.latest_leaders()["RU"].head_of_state.name == "B"


def test_profile_groups_ranks_and_energy_role() -> None:
    seed()
    p = profile("ru")
    assert p["name"] == "Russia" and p["leadership"]["head_of_state"]["name"] == "Vladimir Putin"
    assert p["leadership"]["nuclear"]["stockpile"] == 4400
    head = {h["id"]: h for h in p["headline"]}
    assert (head["population"]["rank"], head["population"]["of"]) == (1, 3)         # PR is a territory: not ranked
    assert head["energy_production"]["value"] == 12000.0 and head["energy_production"]["rank"] == 1
    assert [f["id"] for f in p["groups"]["energy"]][0] == "energy_production"
    assert p["groups"]["economy"][0]["year"] == 2025 and p["groups"]["trade"] == []
    assert p["energy_role"]["surplus"] == ["oil", "gas"] and p["energy_role"]["deficit"] == []
    assert profile("DE")["energy_role"]["deficit"] == ["oil"] and profile("zz") == {}


def test_empty_store_gives_empty_groups() -> None:
    p = profile("FR")
    assert p["headline"] == [] and all(v == [] for v in p["groups"].values())


def test_compare_shares_one_scale() -> None:
    seed()
    c = compare(["RU", "DE", "UA"])
    pop = next(m for m in c["metrics"] if m["id"] == "population")
    assert pop["max"] == 143e6 and [r["iso2"] for r in pop["rows"]] == ["RU", "DE", "UA"]
    gdp = next(m for m in c["metrics"] if m["id"] == "gdp")
    assert [r["iso2"] for r in gdp["rows"]] == ["RU", "DE"]                           # UA has no GDP stored: simply absent
    assert [a["name"] for a in c["actors"]] == ["Russia", "Germany", "Ukraine"]


def test_evidence_block_is_one_cited_line_per_actor() -> None:
    seed()
    text = evidence_block(["RU", "DE"])
    lines = text.splitlines()
    assert len(lines) == 3 and "ACTORS ON RECORD" in lines[0]
    ru = lines[1]
    assert "Vladimir Putin (head of state)" in ru and "population 143M (2025)" in ru and "GDP $2.5T (2025)" in ru
    assert "military spending $149B (2024) = 7.1% of GDP" in ru and "4,400 warheads" in ru and "produces more than it uses: oil, gas" in ru
    assert evidence_block(["nowhere"]) == ""
