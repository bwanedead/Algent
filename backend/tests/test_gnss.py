"""GNSS interference: aircraft filtering and tally, zones/severity/flags against a cell's own history, GPSJam parsing and the H3 decoder, collector (offline), publish shape."""

from __future__ import annotations

import json
from datetime import UTC, date, datetime

import pytest

from algent_backend.gnss import collect, derive, desk, flags, gpsjam, h3, store, zones
from algent_backend.gnss import publish as pub
from algent_backend.gnss.contracts import Zone


@pytest.fixture(autouse=True)
def _root(tmp_path, monkeypatch):
    monkeypatch.setenv("ALGENT_GNSS_STORE", str(tmp_path / "gs"))


def ac(hexid, lat, lon, nac_p, **kw):
    return {"hex": hexid, "type": "adsb_icao", "lat": lat, "lon": lon, "nac_p": nac_p, "version": 2, "alt_baro": 35000, **kw}


def test_only_adsb_v2_airborne_aircraft_count():
    assert derive.usable(ac("a", 55.1, 20.2, 9))
    assert not derive.usable({**ac("a", 55.1, 20.2, 0), "type": "mlat"})            # position computed on the ground: NIC is always 0
    assert not derive.usable({**ac("a", 55.1, 20.2, 0), "version": 0})              # v0 transponders carry no NACp
    assert not derive.usable({**ac("a", 55.1, 20.2, 0), "alt_baro": "ground"})
    assert not derive.usable({"hex": "a", "type": "adsb_icao", "lat": 1.0, "lon": 1.0, "version": 2})   # no NACp at all


def test_tally_cells_degraded_and_overlap_dedupe():
    planes = [ac("a", 55.1, 20.2, 9), ac("b", 55.9, 20.7, 0), ac("b", 55.9, 20.7, 0), ac("c", 55.5, 20.5, 6), ac("d", 40.2, -75.5, 10)]
    t = derive.tally(planes)
    assert t == {"55,20": [3, 2], "40,-76": [1, 0]}                                  # "b" seen by two probe circles counts once; NACp 6 < 7 is degraded


def test_cell_center_and_negative_cells():
    assert derive.cell_center("55,20") == (55.5, 20.5) and derive.cell_of(-33.8, -70.2) == "-34,-71"


def test_severity_bands():
    assert [zones.severity(s) for s in (0.03, 0.15, 0.5)] == ["low", "medium", "high"]


def put_day(day, cell, n, bad, hours=1):
    for _ in range(hours):
        store.append_hour(day, {cell: [n, bad]}, probes=27, aircraft=n)


def test_zone_needs_observations_share_and_degraded_floor():
    t = {"55,20": [40, 12], "50,5": [40, 1], "60,30": [5, 5], "10,10": [100, 2]}
    zs = zones.build("2026-10-20", today=date(2026, 10, 20), tally=t, country=lambda *_: "")
    assert [z.cell for z in zs] == ["55,20"]                                          # 1/40 is background, 5 obs too few, 2/100 under the degraded floor
    z = zs[0]
    assert (z.severity, z.degraded_share, z.basis, z.source) == ("high", 0.3, "our_estimate", "ohmega_adsb") and "minimum" in z.coverage_note


def test_flags_wait_for_a_baseline_then_mark_new_and_intensifying():
    cell = "55,20"
    today = date(2026, 10, 28)
    for d in range(14, 22):                                   # eight closed days of a quiet cell
        put_day(f"2026-10-{d}", cell, 30, 0)
    for d in range(14, 22):                                   # ...and a cell that was already elevated (closed days are cached once read)
        put_day(f"2026-10-{d}", "56,21", 30, 3 + d % 2)
    quiet = zones.build("2026-10-28", today=today, tally={cell: [30, 6]}, country=lambda *_: "")[0]
    assert quiet.flag == "new" and quiet.baseline_since == "2026-10-14"
    jump = zones.build("2026-10-28", today=today, tally={"56,21": [30, 20]}, country=lambda *_: "")[0]
    assert jump.flag == "intensifying"
    steady = zones.build("2026-10-28", today=today, tally={"56,21": [30, 4]}, country=lambda *_: "")[0]
    assert steady.flag == ""
    # before FLAG_AFTER_DAYS closed days of history nothing is flagged
    young = zones.build("2026-10-17", today=date(2026, 10, 17), tally={cell: [30, 6]}, country=lambda *_: "")[0]
    assert young.flag == ""


def test_h3_decoder_matches_known_cells():
    lat, lon = h3.center("85283473fffffff")                # H3 documentation example: contains 37.3615593, -122.0553238
    assert abs(lat - 37.34579) < 1e-4 and abs(lon + 121.97638) < 1e-4
    lat, lon = h3.center("8928308280fffff")
    assert abs(lat - 37.7767) < 1e-3 and abs(lon + 122.4185) < 1e-3
    assert h3.center("not-hex") is None


def test_h3_pentagon_base_cell_is_refused():
    base4 = (1 << 59) | (4 << 52) | (4 << 45) | ((1 << 45) - 1)
    assert h3.center(base4) is None                       # base cell 4 is a pentagon: never guessed


def test_gpsjam_parse_filters_and_decodes():
    lines = ["hex,count_good_aircraft,count_bad_aircraft", "841f715ffffffff,2,6", "841f715ffffffff,50,0", "8400533ffffffff,1,0", "garbage", "841f425ffffffff,9,1"]
    zs = gpsjam.parse(lines, "2026-10-19", country=lambda *_: "LT")
    assert [(z.cell, z.degraded_share, z.severity, z.country, z.basis) for z in zs] == [("841f715ffffffff", 0.75, "high", "LT", "third_party")]
    assert 54 < zs[0].lat < 57 and 20 < zs[0].lon < 23     # Lithuania / Kaliningrad


def test_gpsjam_steps_back_to_the_day_that_exists():
    from algent_backend.polite_http import SourceError

    def lines(url):
        if "2026-10-19" in url:
            yield from ["hex,a,b", "841f715ffffffff,2,6"]
        else:
            raise SourceError("404")

    day, zs = gpsjam.fetch(date(2026, 10, 21), lines=lines)
    assert day == "2026-10-19" and len(zs) == 1


def test_cross_check_marks_agreement():
    base = dict(date="d", source="ohmega_adsb", size_deg=1.0, severity="high", aircraft=20, basis="our_estimate")
    ours = [Zone(id="1", cell="55,20", lat=55.5, lon=20.5, degraded_share=0.3, **base), Zone(id="2", cell="40,10", lat=40.5, lon=10.5, degraded_share=0.3, **base)]
    theirs = [Zone(id="g", date="d", source="gpsjam", cell="x", lat=55.6, lon=20.9, size_deg=0.25, severity="high", degraded_share=0.5, aircraft=10, basis="third_party")]
    zones.cross_check(ours, theirs)
    assert [z.cross_check for z in ours] == ["agrees", "not_in_gpsjam"]
    zones.cross_check(ours[:1], [])                       # no GPSJam file read: nothing changes
    assert ours[0].cross_check == "agrees"


def test_collector_offline_pass_writes_hour_zones_and_status(monkeypatch):
    monkeypatch.setattr(flags, "PROBES", (("a", 55.0, 20.5), ("b", 50.0, 5.0)))
    planes = [ac(f"h{i}", 55.2, 20.4, 0) for i in range(8)] + [ac(f"k{i}", 55.3, 20.6, 9) for i in range(8)]
    out = collect.run(now=datetime(2026, 10, 20, 12, 0, tzinfo=UTC), fetch=lambda url, **k: json.dumps({"ac": planes}), with_gpsjam=False)
    assert out["adsb"]["status"] == "ok" and out["adsb"]["probes"] == 2 and out["adsb"]["aircraft"] == 16
    doc = store.load_zones("2026-10-20")
    assert doc["samples"] == 1 and doc["zones"][0]["severity"] == "high" and doc["baseline_since"] == "2026-10-20"
    assert store.load_status()["ohmega_adsb"]["last_ok"]


def test_collector_records_failure_without_raising():
    out = collect.run(now=datetime(2026, 10, 20, 12, 0, tzinfo=UTC), fetch=lambda url, **k: "not json", with_gpsjam=False)
    assert out["adsb"]["status"] == "error" and store.load_status()["ohmega_adsb"]["last_error"]


def _save(day="2026-10-20", gpsjam=None):
    base = dict(date=day, size_deg=1.0, country="LT", aircraft=20)
    ours = Zone(id="z1", source="ohmega_adsb", cell="55,20", lat=55.5, lon=20.5, severity="high", degraded_share=0.4, basis="our_estimate", baseline_since="2026-10-14", flag="new",
                cross_check="agrees", **base)
    top = Zone(id="z3", source="gpsjam", cell="h2", lat=2.0, lon=2.0, severity="high", degraded_share=0.6, basis="third_party", **base)
    store.save_zones(day, {"date": day, "generated_at": "t", "baseline_since": "2026-10-14", "baseline_days": 6, "samples": 20, "zones": [ours.model_dump()],
                           "gpsjam": [top.model_dump()] if gpsjam is None else gpsjam})
    return ours, top


def test_gpsjam_keeps_only_its_top_band():
    lines = ["841f715ffffffff,2,6", "841f425ffffffff,40,4", "841f725ffffffff,30,5"]          # 75%, 9% (below the band) and 14%
    zs = gpsjam.parse(lines, "2026-10-19", country=lambda *_: "")
    assert sorted(z.degraded_share for z in zs) == [0.1429, 0.75]


def test_stored_zones_drop_per_source_constants_and_read_back_whole():
    _save()
    raw = json.loads((store.root() / "zones" / "2026-10-20.json").read_text(encoding="utf-8"))
    assert "coverage_note" not in raw["zones"][0] and "baseline_since" not in raw["zones"][0]
    z = store.load_zones("2026-10-20")["zones"][0]
    assert "minimum" in z["coverage_note"] and z["baseline_since"] == "2026-10-14"


def test_latest_document_rows_history_and_contract():
    from algent_backend.contracts import spec
    from algent_backend.contracts.shapes import SHAPES

    _save("2026-10-19")
    _save("2026-10-20")
    doc = pub.documents(date(2026, 10, 21))["gnss/latest.json"]
    assert doc["day"] == "2026-10-20" and doc["ours"][0]["on_date"] == "2026-10-20" and doc["gpsjam"][0]["source"] == "gpsjam"
    assert [h["day"] for h in doc["history"]] == ["2026-10-19", "2026-10-20"] and doc["history"][0] == {"day": "2026-10-19", "zones": 1, "high": 1, "flagged": 1}
    assert "coverage_note" not in doc["ours"][0] and "minimum" in doc["coverage"]["ohmega_adsb"]
    assert spec.validate(doc, SHAPES["ohmega.gnss.latest"]) == [] and doc == pub.documents(date(2026, 10, 21))["gnss/latest.json"]
    assert pub.documents(date(2026, 10, 1)) == {}


def test_publish_builds_documents_and_overlay(monkeypatch):
    _save()
    got, over = {}, {}
    monkeypatch.setattr(pub.site_data, "publish_built", lambda build, **k: got.update(build()) or {"ok": True})
    monkeypatch.setattr("algent_backend.live.snapshots.publish", lambda docs, **k: over.update(docs) or {"ok": True})
    out = pub.publish(today=date(2026, 10, 21))
    assert out["files"]["ok"] and "gnss/latest.json" in got and over["gnss"]["zones"][0]["src"] == "o"


def test_retention_keeps_sums_drops_hours_and_compacts_old_gpsjam():
    today = date(2026, 11, 20)
    put_day("2026-11-01", "55,20", 30, 6)                                          # 19 days old: past the hour window
    put_day("2026-11-19", "55,20", 30, 6)
    _save("2026-10-01")                                                              # 50 days old: GPSJam's cells go, ours stay
    _save("2026-11-15")
    _save("2024-01-01")                                                              # past the 400-day cap
    out = store.prune(today)
    assert out["compacted"] == 1 and out["dropped"] >= 2
    assert not (store.root() / "hours" / "2026-11-01.jsonl").exists() and (store.root() / "hours" / "2026-11-19.jsonl").exists()
    assert store.day_tally("2026-11-01", today) == {"55,20": [30, 6]}              # the baseline reads the sums: nothing it needs was lost
    assert store.load_zones("2026-10-01")["gpsjam"] == [] and store.load_zones("2026-10-01")["zones"] and store.load_zones("2026-11-15")["gpsjam"]
    assert "2024-01-01" not in store.zone_days()


def test_collect_prunes_after_every_pass(monkeypatch):
    monkeypatch.setattr(flags, "PROBES", (("a", 55.0, 20.5),))
    put_day("2026-10-01", "55,20", 30, 0)
    out = collect.run(now=datetime(2026, 10, 20, 12, 0, tzinfo=UTC), fetch=lambda url, **k: json.dumps({"ac": [ac("h1", 55.2, 20.4, 9)]}), with_gpsjam=False)
    assert out["retention"]["dropped"] == 1


def test_snapshot_doc_is_compact_and_carries_provenance():
    _save(gpsjam=[Zone(id="z2", date="2026-10-20", source="gpsjam", cell="h", lat=1.0, lon=1.0, size_deg=0.25, severity="high", degraded_share=0.5, aircraft=10,
                       basis="third_party").model_dump()])
    doc = pub.snapshot_doc(date(2026, 10, 21))
    assert doc["zones"][0] == {"lat": 55.5, "lon": 20.5, "r": 1.0, "s": "high", "share": 0.4, "f": "new", "src": "o"} and doc["zones"][1]["src"] == "g"
    assert doc["p"]["ours"]["basis"] == "our_estimate" and doc["p"]["ours"]["baseline_since"] == "2026-10-14" and "minimum" in doc["p"]["ours"]["coverage_note"]
    assert pub.snapshot_doc(date(2026, 10, 1)) is None
