"""Conflict event log: GDELT parsing/merge/filters, dedupe across files and days, keyed-source parsers, collector (offline fakes), asset join, publish shape, desk."""

from __future__ import annotations

import json
from datetime import date

import pytest

from algent_backend.conflict import assets, desk, flags, store
from algent_backend.conflict import collect as collect_mod
from algent_backend.conflict import publish as pub
from algent_backend.conflict.contracts import ConflictEvent, event_id
from algent_backend.conflict.sources import NeedsKey, acled, gdelt, reliefweb, ucdp


@pytest.fixture(autouse=True)
def _root(tmp_path, monkeypatch):
    monkeypatch.setenv("ALGENT_CONFLICT_STORE", str(tmp_path / "cs"))
    assets._default_bands.cache_clear()


def row(*, eid="1", day="20261020", root="19", base="190", a1="UAF", a2="RUS", geo_type="4", feature="F1", lat="48.5", lon="37.9", cc="UP",
        arts="3", url="https://x.example/a", place="Bakhmut, Donetsk, Ukraine") -> str:
    f = [""] * 61
    f[0], f[1], f[5], f[6], f[15], f[16] = eid, day, a1, "UKRAINE ARMED", a2, "RUSSIA ARMED"
    f[27], f[28], f[33] = base, root, arts
    f[51], f[52], f[53], f[56], f[57], f[58], f[60] = geo_type, place, cc, lat, lon, feature, url
    return "\t".join(f)


def test_gdelt_filters_roots_geo_precision_and_articles():
    lines = [row(), row(root="04", base="040"), row(geo_type="1"), row(feature="F2", arts="1")]
    evs = gdelt.parse(lines, "t")
    assert len(evs) == 1                                    # protest-class row, centroid geocode and single-article row are dropped
    e = evs[0]
    assert (e.type, e.country, e.coding, e.basis, e.fatalities) == ("armed_clash", "UA", "machine", "third_party", None)
    assert e.confidence == "low" and "Machine-coded" in e.coverage_note and e.date == "2026-10-20"


def test_gdelt_merges_same_event_and_sums_articles():
    evs = gdelt.parse([row(arts="3"), row(eid="2", arts="4", url="https://y.example/b")], "t")
    assert len(evs) == 1 and evs[0].articles == 7 and evs[0].confidence == "medium" and len(evs[0].urls) == 2


@pytest.mark.parametrize(("base", "kind"), [("1831", "bombing"), ("195", "airstrike"), ("193", "armed_clash"), ("203", "mass_violence"), ("186", "assault")])
def test_gdelt_types(base, kind):
    assert gdelt.kind_of(base) == kind


def test_gdelt_cap_keeps_most_reported(monkeypatch):
    monkeypatch.setattr(flags, "GDELT_MAX_PER_FILE", 2)
    evs = gdelt.parse([row(feature=f"F{i}", arts=str(i + 2)) for i in range(5)], "t")
    assert [e.articles for e in evs] == [6, 5]


def test_stamps_after_catches_up_in_order_and_is_bounded():
    assert gdelt.stamps_after("20261020080000", "20261020084500") == ["20261020081500", "20261020083000", "20261020084500"]
    assert gdelt.stamps_after("", "20261020084500") == ["20261020084500"]
    assert len(gdelt.stamps_after("20260101000000", "20261020084500")) == flags.GDELT_CATCHUP_FILES


def test_dedupe_across_files_and_adjacent_days():
    first = gdelt.parse([row()], "t")
    assert len(collect_mod.novel(first)) == 1
    store.append(first)
    again = gdelt.parse([row(eid="9", url="https://z.example/c")], "t")
    assert collect_mod.novel(again) == []                   # the same event in a later file
    next_day = gdelt.parse([row(day="20261021")], "t")
    assert collect_mod.novel(next_day) == []                # re-reported a day later
    far = gdelt.parse([row(day="20261030")], "t")
    assert len(collect_mod.novel(far)) == 1                 # ten days later is a new event


def test_store_is_append_only_and_tracks_since():
    e = gdelt.parse([row()], "t")
    assert len(store.append(e)) == 1 and store.append(e) == []
    assert store.line_count() == 1 and store.collecting_since() == date.today().isoformat()
    (store.shard_path("2026-10-20")).open("a").write("not json\n")
    assert len(store.shard("2026-10-20")) == 1              # a torn line does not hide the rest


def test_collector_cursor_dedupe_and_needs_key(monkeypatch):
    for k in ("ALGENT_RELIEFWEB_APPNAME", "ALGENT_ACLED_EMAIL", "ALGENT_ACLED_PASSWORD", "ALGENT_UCDP_TOKEN"):
        monkeypatch.delenv(k, raising=False)
    files = {"20261020083000": [row()], "20261020084500": [row(eid="2", url="https://q.example/")]}
    report = collect_mod.collect(fetchers={"gdelt_latest": lambda: "20261020084500", "gdelt_file": lambda s: gdelt.parse(files.get(s, []), "t")})
    by = {r["source"]: r for r in report["sources"]}
    assert by["gdelt"]["status"] == "ok" and by["gdelt"]["new"] == 1       # the second file repeats the first event
    assert store.load_cursor()["gdelt"] == "20261020084500"
    assert {by[s]["status"] for s in ("reliefweb", "acled", "ucdp")} == {"needs-key"}
    assert "since" in json.dumps(store.since()) or store.since()["gdelt"]


def test_reliefweb_parse_and_key_required(monkeypatch):
    body = json.dumps({"data": [{"id": 7, "fields": {"title": "Sudan: Attack on market kills 20", "date": {"created": "2026-10-19T10:00:00+00:00"},
                                                       "country": [{"name": "Sudan", "iso3": "SDN", "primary": True}], "url": "https://reliefweb.int/r/7",
                                                       "source": [{"name": "OCHA"}]}}]})
    [e] = reliefweb.parse(body, "t")
    assert (e.type, e.country, e.basis, e.coding, e.lat) == ("report", "SD", "official", "report", None)
    monkeypatch.delenv("ALGENT_RELIEFWEB_APPNAME", raising=False)
    with pytest.raises(NeedsKey):
        reliefweb.fetch("t", get=lambda *a, **k: "")


def test_acled_parse_keeps_violence_only():
    body = json.dumps({"data": [
        {"event_id_cnty": "SYR1", "event_date": "2026-10-18", "event_type": "Explosions/Remote violence", "sub_event_type": "Air/drone strike", "actor1": "Russian forces",
         "actor2": "Civilians", "country": "Syria", "location": "Idlib", "admin1": "Idlib", "latitude": "35.9", "longitude": "36.6", "fatalities": "4", "notes": "Air strike on a market."},
        {"event_id_cnty": "SYR2", "event_date": "2026-10-18", "event_type": "Protests", "sub_event_type": "Peaceful protest", "country": "Syria", "latitude": "35", "longitude": "36"}]})
    evs = acled.parse(body, "t")
    assert len(evs) == 1 and (evs[0].type, evs[0].fatalities, evs[0].coding, evs[0].confidence, evs[0].country) == ("airstrike", 4, "curated", "high", "SY")


def test_ucdp_parse_and_versions():
    body = json.dumps({"Result": [{"id": 5, "date_start": "2026-10-10 00:00:00", "type_of_violence": 3, "side_a": "Govt", "side_b": "Civilians", "country": "Nigeria",
                                   "latitude": 12.9, "longitude": 13.1, "best": 11, "adm_1": "Borno", "where_coordinates": "Gudumbali"}]})
    [e] = ucdp.parse(body, "t")
    assert (e.type, e.fatalities, e.date, e.country, e.coding) == ("assault", 11, "2026-10-10", "NG", "curated")
    assert ucdp.versions(date(2026, 1, 15)) == ["26.0.1", "25.0.12", "25.0.11"]


class _Asset:
    def __init__(self, id, name, type, lat, lon):
        self.id, self.name, self.type, self.lat, self.lon = id, name, type, lat, lon


class _Ledger:
    def live(self):
        return [_Asset("a1", "Bakhmut substation", "substation", 48.51, 37.9), _Asset("a2", "Far plant", "power_plant", 40.0, 30.0)]


def test_asset_join_only_within_range():
    near, far = gdelt.parse([row()], "t")[0], gdelt.parse([row(feature="F9", lat="50.0", lon="30.0")], "t")[0]
    assert assets.attach([near, far], _Ledger()) == 1
    assert near.assets[0].id == "a1" and near.assets[0].km < 2 and far.assets == []


def test_publish_rows_respect_cap_watermark_and_shape(monkeypatch):
    monkeypatch.setattr(flags, "PUBLISH_PER_DAY", 2)
    store.append(gdelt.parse([row(feature=f"F{i}", arts=str(i + 2)) for i in range(4)], "t"))
    sent: list = []

    class Cur:
        def executemany(self, sql, rows): sent.extend(rows)
        def __enter__(self): return self
        def __exit__(self, *a): return False

    class Conn(Cur):
        def cursor(self): return Cur()
        def commit(self): pass

    out = pub.publish(today=date(2026, 10, 21), connect=lambda: Conn())
    assert out["events"] == 2 and [r[13] for r in sent] == [5, 4]      # the two most-reported; `articles` column
    assert len(sent[0]) == 21 and sent[0][18] == "third_party"          # basis column present
    assert pub.publish(today=date(2026, 10, 21), connect=lambda: Conn())["events"] == 0


def test_desk_block_marks_basis_and_minimum():
    today = date.today().isoformat()
    ev = ConflictEvent(id=event_id("acled", "A", today), source="acled", date=today, observed_at="t", type="airstrike", country="UA", place="Kharkiv",
                       fatalities=3, coding="curated", confidence="high", basis="third_party", urls=["https://acleddata.com/x"])
    store.append([ev])
    text, urls, n = desk.block({"UA"})
    assert n == 1 and "MINIMUM" in text and "collected since" in text and "killed per acled" in text and "https://acleddata.com/x" in urls
    assert desk.block({"FR"}) == ("", set(), 0)
