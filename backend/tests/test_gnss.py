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


def test_publish_shape_and_gpsjam_floor():
    base = dict(date="2026-10-20", size_deg=1.0, country="LT", aircraft=20)
    ours = Zone(id="z1", source="ohmega_adsb", cell="55,20", lat=55.5, lon=20.5, severity="high", degraded_share=0.4, basis="our_estimate", baseline_since="2026-10-14", **base)
    low = Zone(id="z2", source="gpsjam", cell="h1", lat=1.0, lon=1.0, severity="low", degraded_share=0.05, basis="third_party", **base)
    top = Zone(id="z3", source="gpsjam", cell="h2", lat=2.0, lon=2.0, severity="high", degraded_share=0.6, basis="third_party", **base)
    store.save_zones("2026-10-20", {"date": "2026-10-20", "generated_at": "t", "zones": [ours.model_dump()], "gpsjam": [low.model_dump(), top.model_dump()]})
    assert [z.id for z in pub.zones_for("2026-10-20")] == ["z1", "z3"]                # GPSJam cells below their top band are not sent
    assert len(pub.row(ours)) == 16 and pub.row(ours)[13] == "our_estimate" and pub.row(ours)[15] == "2026-10-14"
    sent: list = []

    class Cur:
        def executemany(self, sql, rows): sent.extend(rows)
        def __enter__(self): return self
        def __exit__(self, *a): return False

    class Conn(Cur):
        def cursor(self): return Cur()
        def commit(self): pass

    assert pub.publish(today=date(2026, 10, 20), connect=lambda: Conn())["zones"] == 2
    assert pub.publish(today=date(2026, 10, 20), connect=lambda: Conn())["zones"] == 0      # unchanged document: nothing resent
    store.save_zones("2026-10-20", {"date": "2026-10-20", "generated_at": "t2", "zones": [ours.model_dump()], "gpsjam": []})
    assert pub.publish(today=date(2026, 10, 20), connect=lambda: Conn())["zones"] == 1      # the open day changed: upserted again


def test_snapshot_doc_is_compact_and_carries_provenance():
    ours = Zone(id="z1", date="2026-10-20", source="ohmega_adsb", cell="55,20", lat=55.5, lon=20.5, size_deg=1.0, severity="high", degraded_share=0.4, aircraft=30,
                flag="new", basis="our_estimate")
    weak = Zone(id="z2", date="2026-10-20", source="gpsjam", cell="h", lat=1.0, lon=1.0, size_deg=0.25, severity="low", degraded_share=0.05, aircraft=10, basis="third_party")
    store.save_zones("2026-10-20", {"date": "2026-10-20", "generated_at": "t", "baseline_since": "2026-10-14", "baseline_days": 6,
                                    "zones": [ours.model_dump()], "gpsjam": [weak.model_dump()]})
    doc = pub.snapshot_doc(date(2026, 10, 21))
    assert doc["zones"] == [{"lat": 55.5, "lon": 20.5, "r": 1.0, "s": "high", "share": 0.4, "f": "new", "src": "o"}]
    assert doc["p"]["ours"]["basis"] == "our_estimate" and doc["p"]["ours"]["baseline_since"] == "2026-10-14" and "minimum" in doc["p"]["ours"]["coverage_note"]
    assert pub.snapshot_doc(date(2026, 10, 1)) is None
