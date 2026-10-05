"""Actors: registry, tagging regression and the four source parsers, offline on captured real payloads."""

from __future__ import annotations

import json
from pathlib import Path

from algent_backend.actors import catalog, registry
from algent_backend.actors.sources import imf, owid, wikidata, worldbank
from algent_backend.publishing import tagging

FX = Path(__file__).parent / "fixtures" / "actors"
AT = "2026-10-04T00:00:00+00:00"


def test_registry_is_the_country_table() -> None:
    assert registry.get("RU").name == "Russia" and registry.get("ru").iso3 == "RUS"
    assert registry.display_name("KR") == "South Korea"
    assert registry.resolve("U.S.") == "US" and registry.resolve("Britain") == "GB"
    assert registry.resolve("Korea, Rep.") == "KR" and registry.resolve("RUS") == "RU"
    assert registry.resolve("the Kremlin") is None and registry.resolve("Hormuz") is None   # names only, never scanning
    assert registry.get("WLD") is None and registry.iso2_of_iso3("EUU") == "EU"             # aggregates are not countries
    assert registry.get("PR").kind == "territory" and registry.get("TW").kind == "state"
    assert len(registry.states()) > 180 and set(registry.G20) <= {c.iso2 for c in registry.states()}


def test_build_rows_drops_aggregates() -> None:
    payload = [
        {"id": "WLD", "iso2Code": "1W", "name": "World", "region": {"value": "Aggregates"}, "capitalCity": ""},
        {"id": "RUS", "iso2Code": "RU", "name": "Russian Federation", "region": {"value": "Europe & Central Asia"},
         "capitalCity": "Moscow"},
    ]
    assert [r["iso2"] for r in registry.build_rows(payload)] == ["RU"]


def test_tagging_resolves_what_it_used_to() -> None:
    old = {"IR": "Iran", "US": "United States", "GB": "United Kingdom", "CD": "Democratic Republic of the Congo",
           "CG": "Republic of the Congo", "KP": "North Korea", "KR": "South Korea", "TR": "Turkey", "CZ": "Czechia",
           "TW": "Taiwan", "VE": "Venezuela", "SS": "South Sudan", "AE": "United Arab Emirates", "EU": "European Union",
           "RU": "Russia", "SY": "Syria", "EG": "Egypt", "YE": "Yemen", "VN": "Vietnam", "NI": "Nicaragua"}
    for iso, name in old.items():
        assert tagging._resolve_country_entry({"iso2": iso}) == (iso, name)
    for name, iso in {"usa": "US", "u.s.": "US", "america": "US", "uk": "GB", "britain": "GB", "democratic republic of the congo": "CD",
                      "european union": "EU", "south korea": "KR", "nicaragua": "NI"}.items():
        assert tagging._resolve_country_entry({"iso2": "", "name": name})[0] == iso
    assert tagging.derive_places({"countries_of_relevance": [{"iso2": "IR", "name": "Iran"}]}) == (["Iran"], ["🇮🇷"])


def test_worldbank_parse_filters_aggregates_and_empty() -> None:
    payload = json.loads((FX / "wb_population.json").read_text(encoding="utf-8"))
    obs = worldbank.parse_indicator(payload, catalog.get("population"), AT)
    assert {o.iso2 for o in obs} == {"RU", "UA", "US"}                # AFE / WLD / blank code dropped
    ru = max((o for o in obs if o.iso2 == "RU"), key=lambda o: o.year)
    assert ru.year == 2025 and ru.value == 143513328 and ru.source == "wb"


def test_worldbank_error_payload_raises() -> None:
    import pytest
    from algent_backend.polite_http import SourceError
    with pytest.raises(SourceError):
        worldbank.parse_indicator([{"message": [{"id": "120", "value": "Invalid"}]}], catalog.get("gdp"), AT)


def test_owid_streams_latest_nonempty_year_per_column() -> None:
    lines = (FX / "owid_energy.csv").read_text(encoding="utf-8").splitlines()
    inds = [catalog.get(i) for i in ("energy_use", "oil_prod", "elec_fossil")]
    got = {(o.iso2, o.indicator): o for o in owid.parse_rows(lines, inds, AT)}
    assert got[("RU", "oil_prod")].year == 2024 and got[("RU", "oil_prod")].value == 6121.835   # 2025 row is blank for it
    assert got[("RU", "elec_fossil")].year == 2025
    assert ("RU", "energy_use") in got and not any(k[0] in ("", "AS") for k in got)           # the Asia region row is skipped


def test_imf_keeps_two_years_and_skips_aggregates() -> None:
    payload = json.loads((FX / "imf_ngdp_rpch.json").read_text(encoding="utf-8"))
    obs = imf.parse_series(payload, catalog.get("gdp_growth_imf"), (2025, 2026), AT)
    assert {(o.iso2, o.year) for o in obs} == {("RU", 2025), ("RU", 2026), ("US", 2025), ("US", 2026)}


def test_wikidata_picks_latest_holder_and_leaders() -> None:
    payload = json.loads((FX / "wikidata_leaders.json").read_text(encoding="utf-8"))
    by = {row.iso2: row for row in wikidata.parse_bindings(payload, AT)}
    assert by["RU"].head_of_state.name == "Vladimir Putin" and by["RU"].head_of_government.name == "Mikhail Mishustin"
    assert by["US"].head_of_state.name == by["US"].head_of_government.name
    assert by["RU"].head_of_state.id.startswith("Q") and by["DE"].head_of_government.since >= "2025"
