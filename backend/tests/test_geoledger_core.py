"""Geoledger core: the append-only store, name matching, the open-data seeds, publishing, and the migration (offline)."""

from __future__ import annotations

import json
from contextlib import contextmanager
from datetime import UTC, datetime

import pytest

from algent_backend.database import available
from algent_backend.geoledger import match, publish, seed_osm, seed_wri
from algent_backend.geoledger.contracts import Asset, StatusEvent, event_id, latest, new_asset_id
from algent_backend.geoledger.store import Ledger, load_marker


def _plant(id_: str, name: str, lat: float = 50.0, lon: float = 30.0, country: str = "UA", **kw) -> Asset:
    return Asset(id=id_, name=name, type="power_plant", country=country, lat=lat, lon=lon, **kw)


def _ev(asset_id: str, day: str, status: str, who: str, **kw) -> StatusEvent:
    return StatusEvent(id=event_id(asset_id, day, status, who), asset_id=asset_id, occurred_on=day, status=status, claimant=who,
                       sources=["https://example.org/a"], **kw)


# -- the store -----------------------------------------------------------------------------------

def test_the_ledger_is_append_only_and_a_revision_supersedes_without_erasing(tmp_path) -> None:
    led = Ledger(tmp_path)
    assert led.add_assets([_plant("wri-1", "Zmiivska")]) == 1
    assert led.add_assets([_plant("wri-1", "Zmiivska")]) == 0                      # unchanged: nothing written
    assert led.add_assets([_plant("wri-1", "Zmiivska", aliases=["Zmiyivska TPP"])]) == 1
    lines = (tmp_path / "assets.jsonl").read_text(encoding="utf-8").splitlines()
    assert len(lines) == 2 and json.loads(lines[0])["aliases"] == []               # the old revision is still on file
    assert Ledger(tmp_path).assets["wri-1"].aliases == ["Zmiyivska TPP"]            # the last wins on read


def test_events_are_stored_once_and_need_a_known_asset(tmp_path) -> None:
    led = Ledger(tmp_path)
    led.add_assets([_plant("wri-1", "Zmiivska")])
    e = _ev("wri-1", "2026-10-03", "claimed_struck", "Russian MoD")
    assert led.add_events([e, e, _ev("nope", "2026-10-03", "claimed_struck", "x")]) == 1
    assert led.add_events([e]) == 0 and len((tmp_path / "events.jsonl").read_text(encoding="utf-8").splitlines()) == 1
    assert Ledger(tmp_path).events[e.id].observed_at                                # stamped when recorded


def test_the_latest_event_describes_the_asset_and_a_claim_is_not_a_confirmation(tmp_path) -> None:
    led = Ledger(tmp_path)
    led.add_assets([_plant("wri-1", "Zmiivska")])
    led.add_events([_ev("wri-1", "2026-10-03", "claimed_struck", "Russian MoD"),
                    _ev("wri-1", "2026-10-03", "reported_damaged", "Ukrenergo"),
                    _ev("wri-1", "2026-10-06", "restored", "Ukrenergo")])
    assert led.status("wri-1").status == "restored"
    assert [e.status for e in led.history("wri-1")][:2] == ["claimed_struck", "reported_damaged"]
    assert latest([_ev("a", "2026-10-03", "claimed_struck", "A"), _ev("a", "2026-10-03", "confirmed_damaged", "B")]).status == "confirmed_damaged"


def test_a_torn_line_does_not_hide_the_rest(tmp_path) -> None:
    led = Ledger(tmp_path)
    led.add_assets([_plant("wri-1", "Zmiivska"), _plant("wri-2", "Burshtyn", lon=24.6)])
    with (tmp_path / "assets.jsonl").open("a", encoding="utf-8") as f:
        f.write('{"id": "torn", "name"\n')
    assert set(Ledger(tmp_path).assets) == {"wri-1", "wri-2"}


# -- matching ------------------------------------------------------------------------------------

def _fleet(tmp_path) -> Ledger:
    led = Ledger(tmp_path)
    led.add_assets([_plant("a", "Darnitsa", 50.4, 30.6), _plant("b", "Kiev CHP-5", 50.5, 30.4), _plant("c", "Kiev CHP-6", 50.6, 30.9),
                    _plant("d", "Trypilska TPP", 50.1, 30.7), _plant("e", "Zmiyivska", 49.6, 36.5),
                    _plant("f", "Darnytska", 50.0, 20.0, country="PL")])
    return led


def test_spelling_variants_meet_and_unit_numbers_are_a_hard_guard(tmp_path) -> None:
    led = _fleet(tmp_path)
    assert match.find(led, ["Darnytska CHP-4"], type_="power_plant", country="UA").asset.id == "a"
    assert match.find(led, ["Zmiivska TPP"], type_="power_plant", country="UA").asset.id == "e"
    assert match.find(led, ["Trypillya TPP"], type_="power_plant", country="UA").asset.id == "d"
    assert match.find(led, ["Kyiv CHP-5"], type_="power_plant", country="UA").asset.id == "b"
    assert match.find(led, ["Kyiv CHP-6"], type_="power_plant", country="UA").asset.id == "c"
    assert match.name_score("CHP-5 Kyiv", "CHP-6 Kyiv") == 0.0
    assert match.find(led, ["Київська ТЕЦ-5"], type_="power_plant", country="UA").asset.id == "b"      # Cyrillic folds


def test_country_and_type_must_agree_and_an_unknown_name_matches_nothing(tmp_path) -> None:
    led = _fleet(tmp_path)
    assert match.find(led, ["Darnytska"], type_="power_plant", country="PL").asset.id == "f"
    assert match.find(led, ["Darnitsa"], type_="refinery", country="UA").asset is None
    assert match.find(led, ["Mariupol steelworks"], type_="power_plant", country="UA").asset is None


def test_two_equally_good_assets_are_refused_not_guessed(tmp_path) -> None:
    led = Ledger(tmp_path)
    led.add_assets([_plant("x", "Burshtyn", 49.0, 24.0), _plant("y", "Burshtin", 49.01, 24.01)])
    hit = match.find(led, ["Burshtyn"], type_="power_plant", country="UA")
    assert hit.asset is None and hit.reason == "ambiguous"


# -- seeds ---------------------------------------------------------------------------------------

WRI = ("country,country_long,name,gppd_idnr,capacity_mw,latitude,longitude,primary_fuel,commissioning_year,owner\n"
       "UKR,Ukraine,Zmiivska,UKR0000123,2175,49.58,36.52,Coal,1960,DTEK\n"
       "UKR,Ukraine,Nowhere,UKR0000124,10,,,Solar,,\n"
       "POL,Poland,Belchatow,POL0000001,5298,51.26,19.33,Coal,1982,PGE\n")


def test_wri_rows_become_licensed_power_plants_and_unplaced_rows_are_skipped(tmp_path) -> None:
    led = Ledger(tmp_path)
    f = tmp_path / "wri.csv"
    f.write_text(WRI, encoding="utf-8")
    assert seed_wri.seed(led, path=f) == {"read": 2, "added": 2, "unchanged": 0}
    z = led.assets["wri-UKR0000123"]
    assert (z.country, z.type, z.attrs["capacity_mw"], z.attrs["fuel"], z.licence) == ("UA", "power_plant", 2175.0, "Coal", "CC BY 4.0")
    assert seed_wri.seed(led, path=f)["added"] == 0                                    # a rerun writes nothing


def test_wri_zip_is_read(tmp_path) -> None:
    import io
    import zipfile
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as z:
        z.writestr("global_power_plant_database.csv", WRI)
    assert "Belchatow" in seed_wri.csv_text(buf.getvalue())


def test_osm_elements_are_mapped_cached_and_deduplicated_against_wri(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("ALGENT_GEOLEDGER_STORE", str(tmp_path))
    led = Ledger(tmp_path)
    f = tmp_path / "wri.csv"
    f.write_text(WRI, encoding="utf-8")
    seed_wri.seed(led, path=f)
    answer = {"elements": [
        {"type": "way", "id": 1, "center": {"lat": 49.585, "lon": 36.52}, "tags": {"name": "Zmiivska TPP", "power": "plant", "plant:output:electricity": "2175 MW"}},
        {"type": "node", "id": 2, "lat": 50.45, "lon": 30.52, "tags": {"name": "Kyiv Port", "name:uk": "Київський порт", "operator": "Ports Co"}},
        {"type": "node", "id": 3, "lat": 50.0, "lon": 30.0, "tags": {"power": "plant"}}]}      # no name: skipped
    calls: list[str] = []
    def fetch(q: str) -> dict:
        calls.append(q)
        plants = [e for e in answer["elements"] if e["tags"].get("power") or e["tags"].get("plant:output:electricity")]
        return {"elements": plants if "power" in q else [e for e in answer["elements"] if e not in plants]}
    now = datetime(2026, 10, 14, tzinfo=UTC)
    r = seed_osm.seed(led, seed_osm.PRESETS["ukraine"], ["power_plant", "port"], fetch=fetch, iso_at=lambda la, lo: "UA", now=now, pause=0)
    assert r["kinds"]["power_plant"]["features"] == 1 and "wri-UKR0000123" in led.assets
    assert "Zmiivska TPP" in led.assets["wri-UKR0000123"].aliases and not any(k.startswith("osm-w1") for k in led.assets)
    assert "osm-n2" in led.assets and led.assets["osm-n2"].type == "port" and led.assets["osm-n2"].licence == "ODbL 1.0"
    seed_osm.seed(led, seed_osm.PRESETS["ukraine"], ["power_plant", "port"], fetch=fetch, iso_at=lambda la, lo: "UA", now=now, pause=0)
    assert len(calls) == 2                                                                       # the second run came from the cache


def test_a_failing_overpass_query_is_reported_and_the_rest_still_run(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("ALGENT_GEOLEDGER_STORE", str(tmp_path))
    def fetch(q: str) -> dict:
        if "refinery" in q:
            raise RuntimeError("busy")
        return {"elements": [{"type": "node", "id": 9, "lat": 1.0, "lon": 1.0, "tags": {"name": "Port One"}}]}
    r = seed_osm.seed(Ledger(tmp_path), [0, 0, 2, 2], ["refinery", "port"], fetch=fetch, iso_at=lambda *_: "", pause=0)
    assert len(r["errors"]) == 1 and r["kinds"]["port"]["added"] == 1


# -- publish -------------------------------------------------------------------------------------

class _Cur:
    def __init__(self, log): self.log = log
    def __enter__(self): return self
    def __exit__(self, *a): return False
    def executemany(self, sql, rows): self.log.append((sql.split("(")[0].strip(), list(rows)))


class _Conn:
    def __init__(self, log): self.log = log
    def __enter__(self): return self
    def __exit__(self, *a): return False
    def cursor(self): return _Cur(self.log)
    def commit(self): self.log.append(("commit", []))


def test_publish_sends_only_what_is_new_and_carries_the_latest_status(tmp_path) -> None:
    led = Ledger(tmp_path)
    led.add_assets([_plant("wri-1", "Zmiivska", attrs={"capacity_mw": 2175.0, "fuel": "Coal"}), _plant("wri-2", "Burshtyn", lon=24.6)])
    led.add_events([_ev("wri-1", "2026-10-03", "claimed_struck", "Russian MoD")])
    log: list = []
    r = publish.publish(led, connect=lambda: _Conn(log))
    assert r == {"db": True, "assets": 2, "events": 1}
    asset_rows = next(rows for sql, rows in log if sql.startswith("insert into geo_assets"))
    z = next(row for row in asset_rows if row[0] == "wri-1")
    assert z[8] == 2175.0 and z[9] == "Coal" and z[14:18] == ("claimed_struck", "2026-10-03", "Russian MoD", 1)
    assert load_marker(tmp_path) == {"assets": 2, "events": 1}
    again: list = []
    assert publish.publish(led, connect=lambda: _Conn(again))["note"] == "nothing new" and again == []
    led.add_events([_ev("wri-1", "2026-10-04", "reported_damaged", "Ukrenergo")])        # a new event refreshes the asset row too
    third: list = []
    assert publish.publish(led, connect=lambda: _Conn(third)) == {"db": True, "assets": 1, "events": 1}
    assert publish.publish(led, full=True, connect=lambda: _Conn([]))["assets"] == 2


def test_publish_is_a_noop_without_a_database(tmp_path, monkeypatch) -> None:
    monkeypatch.delenv("DATABASE_URL", raising=False)
    led = Ledger(tmp_path)
    led.add_assets([_plant("wri-1", "Zmiivska")])
    assert publish.publish(led)["db"] is False and load_marker(tmp_path) == {"assets": 0, "events": 0}


def test_a_failed_publish_does_not_move_the_watermark(tmp_path) -> None:
    led = Ledger(tmp_path)
    led.add_assets([_plant("wri-1", "Zmiivska")])
    @contextmanager
    def boom():
        raise RuntimeError("down")
        yield
    assert publish.publish(led, connect=boom)["db"] is False
    assert load_marker(tmp_path)["assets"] == 0


# -- migration -----------------------------------------------------------------------------------

def test_the_geoledger_migration_is_public_read_only() -> None:
    sql = next(p for p in available() if p.stem == "009_geoledger").read_text(encoding="utf-8")
    for table in ("geo_assets", "geo_asset_events"):
        assert f"alter table {table}" in sql.replace("       ", " ") or f"alter table {table} " in sql
        assert f"grant select on {table}" in sql.replace("  ", " ").replace("  ", " ") or f"grant select on {table} " in sql
    assert sql.count("enable row level security") == 2
    assert "revoke insert, update, delete, truncate on geo_assets, geo_asset_events from anon, authenticated" in sql
    assert "for select to anon" in sql and "to anon using (true)" in sql
    assert "grant insert" not in sql and "grant all" not in sql and "grant update" not in sql
    assert new_asset_id("Zmiivska TPP", "power_plant", "UA") == "og-ua-power_plant-zmiivska-tpp"
