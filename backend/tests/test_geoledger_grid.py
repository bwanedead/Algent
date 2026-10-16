"""Geoledger alias layer, merges and the grid-impact rollup (offline)."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from algent_backend.geoledger import alias, grid, ingest
from algent_backend.geoledger import extract as ex
from algent_backend.geoledger.contracts import Asset, StatusEvent, event_id
from algent_backend.geoledger.materials import Item, Material
from algent_backend.geoledger.store import Ledger


def _plant(id_: str, name: str, mw: float | None = None, fuel: str = "Coal", country: str = "UA", **kw) -> Asset:
    attrs = {**({"capacity_mw": mw} if mw else {}), "fuel": fuel}
    return Asset(id=id_, name=name, type="power_plant", country=country, lat=50.0, lon=30.0, attrs=attrs, **kw)


def _ev(asset_id: str, day: str, status: str, who: str) -> StatusEvent:
    return StatusEvent(id=event_id(asset_id, day, status, who), asset_id=asset_id, occurred_on=day, status=status, claimant=who,
                       sources=["https://example.org/a"])


def _cand(**kw) -> ex.Candidate:
    base = dict(name="x", type="power_plant", country="UA", status="claimed_struck", claimant="Russian MoD",
                occurred_on="2026-10-03", sources=["https://example.org/a"], item_ids=["d1"])
    return ex.Candidate(**{**base, **kw})


def _m() -> Material:
    return Material(label="t", via="daily:2026-10-03:thr", default_date="2026-10-03", items=(Item(id="d1", text="x"),))


# -- aliases --------------------------------------------------------------------------------------

@pytest.mark.parametrize("written", ["Kyiv CHP-5", "Kyiv TEC-5", "Kyiv TETs-5", "Київська ТЕЦ-5", "ТЕЦ-5 Київ", "Kyivska TPP 5", "Kyiv CHP5"])
def test_unit_numbers_and_plant_kind_words_are_equivalent_spellings(tmp_path, written) -> None:
    led = Ledger(tmp_path)
    led.add_assets([_plant("wri-5", "Kyiv CHP-5"), _plant("wri-6", "Kyiv CHP-6")])
    assert alias.find(led, [written], type_="power_plant", country="UA").asset.id == "wri-5"


def test_curated_groups_join_spellings_no_rule_can(tmp_path) -> None:
    led = Ledger(tmp_path)
    led.add_assets([_plant("wri-t", "Trypilska TES"), _plant("wri-d", "Kyiv CHP-4"), _plant("wri-z", "Zaporizhia Nuclear Power Plant", fuel="Nuclear")])
    assert alias.find(led, ["Trypillya TPP"], type_="power_plant", country="UA").asset.id == "wri-t"
    assert alias.find(led, ["Дарницька ТЕЦ"], type_="power_plant", country="UA").asset.id == "wri-d"
    assert alias.find(led, ["ZNPP"], type_="power_plant", country="UA").asset.id == "wri-z"


def test_a_unit_only_name_needs_a_place_or_a_single_candidate(tmp_path) -> None:
    led = Ledger(tmp_path)
    led.add_assets([_plant("kyiv5", "Kyiv CHP-5"), _plant("kharkiv5", "Kharkiv CHP-5"), _plant("lviv6", "Lviv CHP-6")])
    assert alias.find(led, ["ТЕЦ-5"], type_="power_plant", country="UA").asset is None          # two CHP-5s: refuse
    assert alias.find(led, ["ТЕЦ-5"], type_="power_plant", country="UA", place="Kyiv").asset.id == "kyiv5"
    assert alias.find(led, ["CHP-6"], type_="power_plant", country="UA").asset.id == "lviv6"    # only one CHP-6 in the country
    assert alias.find(led, ["CHP-6"], type_="power_plant", country="PL").asset is None


def test_plant_kind_and_unit_are_guards(tmp_path) -> None:
    led = Ledger(tmp_path)
    led.add_assets([_plant("hpp", "Dnipro HPP", fuel="Hydro"), _plant("chp", "Dnipro CHP-1")])
    assert alias.find(led, ["Dnipro HPP"], type_="power_plant", country="UA").asset.id == "hpp"
    assert alias.find(led, ["Dnipro CHP-9"], type_="power_plant", country="UA").asset is None


def test_extraction_does_not_mint_a_duplicate_when_an_alias_resolves(tmp_path) -> None:
    led = Ledger(tmp_path)
    led.add_assets([_plant("wri-t", "Trypilska TES")])
    a, created = ingest.resolve(led, _cand(name="Трипільська ТЕС"), _m())
    assert a.id == "wri-t" and not created and len(led.assets) == 1
    a, created = ingest.resolve(led, _cand(name="Trypillya TPP"), _m())
    assert a.id == "wri-t" and not created


# -- merge ----------------------------------------------------------------------------------------

def _merged(tmp_path) -> Ledger:
    led = Ledger(tmp_path)
    led.add_assets([_plant("og-dup", "Burshtyn TPP", country="UA"), _plant("wri-b", "Burshtynska", 2300.0)])
    led.add_events([_ev("og-dup", "2026-10-03", "claimed_struck", "Russian MoD"), _ev("wri-b", "2026-10-04", "reported_damaged", "Ukrenergo")])
    led.merge("og-dup", "wri-b", note="same plant")
    return led


def test_merge_keeps_history_and_reads_it_under_the_target(tmp_path) -> None:
    led = _merged(tmp_path)
    assert [e.status for e in led.history("wri-b")] == ["claimed_struck", "reported_damaged"]
    assert led.history("og-dup") == led.history("wri-b") and led.status("og-dup").status == "reported_damaged"
    assert "Burshtyn TPP" in led.assets["wri-b"].aliases and "og-dup" in led.assets          # the duplicate's lines stay on file
    assert "og-dup" not in {a.id for a in led.live()} and led.counts()["merged"] == 1
    lines = (tmp_path / "events.jsonl").read_text(encoding="utf-8").splitlines()
    assert len(lines) == 2 and json.loads(lines[0])["asset_id"] == "og-dup"                    # no event line rewritten
    again = Ledger(tmp_path)                                                                    # survives a reload
    assert again.canonical("og-dup") == "wri-b" and len(again.history("wri-b")) == 2


def test_merge_redirects_new_events_and_dedupes_a_rediscovered_claim(tmp_path) -> None:
    led = _merged(tmp_path)
    assert led.add_events([_ev("og-dup", "2026-10-03", "claimed_struck", "Russian MoD")]) == 0     # the same claim, found under the old id
    assert led.add_events([_ev("og-dup", "2026-10-05", "confirmed_damaged", "IAEA")]) == 1
    assert led.status("wri-b").status == "confirmed_damaged"
    assert ingest.resolve(led, _cand(name="Burshtyn TPP"), _m())[0].id == "wri-b"
    assert [a.id for a in led.candidates({"bur"}, "UA")] == ["wri-b"]


def test_merge_refuses_nonsense(tmp_path) -> None:
    led = _merged(tmp_path)
    for dup, into in (("og-dup", "wri-b"), ("wri-b", "og-dup"), ("wri-b", "wri-b"), ("nope", "wri-b")):
        with pytest.raises(ValueError):
            led.merge(dup, into)


# -- rollup ---------------------------------------------------------------------------------------

def _fleet(tmp_path) -> Ledger:
    led = Ledger(tmp_path)
    led.add_assets([_plant("a", "Alpha TPP", 1000.0), _plant("b", "Beta HPP", 500.0, "Hydro"), _plant("c", "Gamma NPP", 2000.0, "Nuclear"),
                    _plant("d", "Delta Solar", 500.0, "Solar"), _plant("e", "Nocap TPP"), _plant("z", "Zed TPP", 900.0, country="PL")])
    led.add_events([
        _ev("a", "2026-10-10", "claimed_struck", "Russian MoD"),
        _ev("b", "2026-10-12", "claimed_struck", "Russian MoD"), _ev("b", "2026-10-13", "confirmed_damaged", "Ukrhydroenergo"),
        _ev("c", "2026-10-11", "claimed_struck", "Russian MoD"), _ev("c", "2026-10-12", "restored", "Energoatom"),
        _ev("e", "2026-10-12", "reported_damaged", "Ukrenergo"),
        _ev("d", "2026-09-01", "claimed_struck", "Russian MoD"),                       # outside both windows
        _ev("z", "2026-10-13", "confirmed_damaged", "PGE")])
    return led


def test_rollup_keeps_claims_and_confirmations_separate_and_shares_right(tmp_path) -> None:
    doc = grid.rollup(_fleet(tmp_path), "UA", "2026-10-15")
    assert doc["installed"]["mw"] == 4000.0 and doc["installed"]["by_fuel"]["thermal"] == 1000.0 and doc["installed"]["plants"] == 5
    w = doc["windows"]["30"]
    assert w["claimed"]["mw"] == 3500.0 and w["claimed"]["share"] == 0.875 and w["claimed"]["plants"] == 3   # a, b, c said; d is outside the window
    assert w["confirmed"]["mw"] == 500.0 and w["confirmed"]["share"] == 0.125 and w["confirmed"]["by_fuel"]["hydro"] == 500.0
    assert w["reported"]["plants"] == 1 and w["reported"]["mw"] == 0.0 and w["reported"]["no_capacity"] == 1   # no capacity: listed, adds no MW
    assert w["restored"]["mw"] == 2000.0
    assert w["buckets"]["confirmed"]["hydro"] == 500.0 and w["buckets"]["claimed"]["thermal"] == 1000.0
    assert w["buckets"]["restored"]["nuclear"] == 2000.0 and sum(w["buckets"]["claimed"].values()) == 1000.0     # b is confirmed, c restored
    assert doc["provenance"] == "ohmega_derived" and any("nameplate" in c for c in doc["caveats"]) and any("no capacity" in c for c in doc["caveats"])
    assert "PL" not in json.dumps(doc["windows"]["30"]["affected"]) and {r["id"] for r in w["affected"]} == {"a", "b", "c", "e"}


def test_rollup_windows_and_series(tmp_path) -> None:
    doc = grid.rollup(_fleet(tmp_path), "UA", "2026-10-15")
    short = doc["windows"]["7"]
    assert short["claimed"]["mw"] == 3500.0 and doc["windows"]["7"]["days"] == 7
    old = grid.rollup(_fleet(tmp_path), "UA", "2026-10-17")["windows"]["7"]                    # the 10-10 claim aged out
    assert old["claimed"]["plants"] == 2 and old["claimed"]["mw"] == 2500.0
    assert len(doc["series"]) == 30 and doc["series"][-1]["day"] == "2026-10-15" and doc["series"][-1]["confirmed_mw"] == 500.0
    assert doc["last_event_on"] == "2026-10-13"


def test_rollup_line_is_citable_and_empty_when_nothing_was_said(tmp_path) -> None:
    led = _fleet(tmp_path)
    text = grid.rollup(led, "UA", "2026-10-15")["line"]
    assert text.startswith("Ohmega analysis, UA grid, 30 days to 2026-10-15") and "claimed struck 3.5 GW (88%)" in text
    assert "damage confirmed or destroyed 500 MW (12%)" in text and "never added" in text
    assert grid.rollup(led, "FR", "2026-10-15")["line"] == "" and grid.rollup(led, "UA", "2026-12-31")["line"] == ""


def test_rollup_ignores_merged_duplicates_and_fuel_classes(tmp_path) -> None:
    led = Ledger(tmp_path)
    led.add_assets([_plant("w", "Wolf TPP", 400.0), _plant("w2", "Wolf Thermal", 400.0)])
    led.add_events([_ev("w2", "2026-10-10", "claimed_struck", "X")])
    led.merge("w2", "w")
    doc = grid.rollup(led, "UA", "2026-10-12")
    assert doc["installed"]["mw"] == 400.0 and doc["windows"]["30"]["claimed"]["plants"] == 1
    assert [grid.fuel_class(f) for f in ("Coal", "Gas", "Hydro", "Nuclear", "Solar", "Wind", "Biomass", "coal;gas", "Storage")] == [
        "thermal", "thermal", "hydro", "nuclear", "renewables", "renewables", "renewables", "thermal", "other"]


def test_publish_rollups_upserts_one_row_per_country_and_is_a_noop_without_db(tmp_path, monkeypatch) -> None:
    from contextlib import contextmanager

    led = _fleet(tmp_path)
    log: list = []

    class _Cur:
        def executemany(self, sql, rows): log.append((sql, list(rows)))
        def __enter__(self): return self
        def __exit__(self, *a): return False

    class _Conn:
        def cursor(self): return _Cur()
        def commit(self): pass
        def rollback(self): pass

    @contextmanager
    def connect():
        yield _Conn()

    assert grid.publish_rollups(led, as_of="2026-10-15", connect=connect)["grid"] == 2
    sql, rows = log[0]
    assert sql.strip().startswith("insert into geo_grid") and {r[0] for r in rows} == {"UA", "PL"}
    assert json.loads(next(r[2] for r in rows if r[0] == "UA"))["windows"]["30"]["confirmed"]["mw"] == 500.0
    monkeypatch.delenv("DATABASE_URL", raising=False)
    assert grid.publish_rollups(led, as_of="2026-10-15")["db"] is False


def test_the_site_serves_the_rollup_and_the_migration_defines_it() -> None:
    from algent_backend.database import available

    sql = next(p for p in available() if p.stem == "010_geo_grid").read_text(encoding="utf-8")
    assert "create table geo_grid" in sql and "enable row level security" in sql and "for select to anon" in sql
    assert "revoke insert, update, delete, truncate on geo_grid from anon, authenticated" in sql
    site = Path(__file__).resolve().parents[2] / "sites" / "ohmega-monster" / "lib"
    assert 'path: "/grid/{iso}"' in (site / "api" / "router.ts").read_text(encoding="utf-8")
    assert '"geo_grid"' in (site / "geoledger.ts").read_text(encoding="utf-8")
