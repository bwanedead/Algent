"""Live world layers: fire grid + notable cells, FIRMS world tiles, the vessel board (bounds, expiry, classes, trails), the sky board,
snapshots, energy and the headline strip."""

from __future__ import annotations

import pytest

pytestmark = pytest.mark.usefixtures("legacy_supabase")

import gzip
import json
from datetime import date, datetime, timezone

import pytest

from algent_backend.instruments import store as istore
from algent_backend.instruments.contracts import Observation
from algent_backend.live import energy, fire_grid, flags, headlines, places, snapshots, store
from algent_backend.live.board import VesselBoard
from algent_backend.live.classify import aircraft_id, flag_of, vessel_class
from algent_backend.live.contracts import Ctx, LiveEvent
from algent_backend.live.feeds import firms
from algent_backend.live.sky import SkyBoard
from algent_backend.live.stream import build_docs

NOW = datetime(2026, 10, 11, 10, 0, tzinfo=timezone.utc)
T = NOW.timestamp()


@pytest.fixture(autouse=True)
def _env(tmp_path, monkeypatch):
    monkeypatch.setenv("ALGENT_INSTRUMENTS_STORE", str(tmp_path / "istore"))
    monkeypatch.setenv("ALGENT_LIVE_STORE", str(tmp_path / "live"))
    monkeypatch.delenv("DATABASE_URL", raising=False)
    monkeypatch.delenv("SUPABASE_URL", raising=False)
    monkeypatch.setattr(places, "country_at", lambda lat, lon: "Nowhere" if lat > 0 else None)


# ── fires ─────────────────────────────────────────────────────────────────────────────────────
def test_fire_grid_folds_detections_and_notable_is_relative_and_deduped():
    g = fire_grid.FireGrid()
    for i in range(1000):                                    # a quiet background: 1000 single weak readings
        g.add(10 + (i % 40) * 0.5, 100 + (i // 40) * 0.5, 3.0)
    for _ in range(30):                                      # one big blaze: many readings in one cell
        g.add(-5.1, 20.1, 80.0)
    g.add(-5.6, 20.4, 500.0)                                 # next to it, a very strong one (same blaze, within 1.5 degrees)
    g.add(60.1, 100.1, 900.0)                                # a separate strong one
    doc = g.doc("t")
    assert doc["detections"] == g.total == 1032 and len(doc["cells"]) == doc["occupied"]
    assert doc["cells"][0][3] == 900 and doc["cells"][0][:2] == [100.125, 60.125]       # strongest first, [lon, lat, n, MW]
    picks = fire_grid.notable(g.rows())
    assert [round(c.frp) for c in picks][:2] == [900, 500]   # the 80 MW x30 cell is the same blaze as the 500 MW one: one event
    assert len(picks) <= flags.MAX_NOTABLE_FIRES
    assert fire_grid.notable(g.rows(), skip=lambda la, lo: True) == []
    assert fire_grid.notable([]) == []


def test_firms_world_tiles_stream_aggregate_and_flag_notables():
    header = "latitude,longitude,acq_date,acq_time,confidence,frp\n"
    rows = {"0,0,90,90": ["48.01,37.01,2026-10-11,0930,h,20.5", "48.02,37.02,2026-10-11,0930,n,5", "48.5,38.5,2026-10-11,0930,l,50",
                          "30.0,60.0,2026-10-11,0800,h,999"],
            "-180,-90,-90,0": ["-30.0,-120.0,2026-10-11,0100,n,2"]}
    seen = []

    def lines(url):
        seen.append(url)
        tile = url.split("VIIRS_SNPP_NRT/")[1].split("/")[0]
        return iter((header + "\n".join(rows.get(tile, [])) + "\n").splitlines())

    res = firms.fetch(Ctx(get=lambda *a, **k: "", now=NOW, key="K", lines=lines))
    assert len(seen) == 8 and all("area/csv/K/VIIRS_SNPP_NRT/" in u for u in seen)      # the whole planet, 8 requests
    doc = res.docs["fires"]
    assert doc["detections"] == 4 and doc["occupied"] == 3                              # the low-confidence row is dropped
    assert next(s.value for s in res.stats if s.series_id == "live_fire_ukraine_front") == 2
    notable = [e for e in res.events if e.data.get("notable")]
    assert notable and notable[0].data["frp_mw"] == 999 and notable[0].severity == "notable" and notable[0].countries == ["Nowhere"]
    assert any(e.id.startswith("firms:ukraine_front") for e in res.events)              # watched-box events stay


def test_firms_skips_a_run_when_the_key_is_out_of_quota():
    def get(url, *a, **k):
        if "mapkey_status" in url:
            return json.dumps({"transaction_limit": 5000, "current_transactions": 4999})
        raise AssertionError("no tile may be requested")

    with pytest.raises(RuntimeError, match="transaction limit"):
        firms.fetch(Ctx(get=get, now=NOW, key="K"))


# ── vessels ───────────────────────────────────────────────────────────────────────────────────
def pos(mmsi, lat, lon, sog=10.0, hdg=90, name=""):
    return {"MetaData": {"MMSI": mmsi, "latitude": lat, "longitude": lon, "ShipName": name},
            "Message": {"PositionReport": {"UserID": mmsi, "Sog": sog, "TrueHeading": hdg, "Cog": 80}}}


def static(mmsi, typ, name="X", dest="ROTTERDAM"):
    return {"MetaData": {"MMSI": mmsi}, "Message": {"ShipStaticData": {"UserID": mmsi, "Type": typ, "Name": name, "Destination": dest}}}


def test_ship_classes_and_flags():
    assert [vessel_class(t) for t in (84, 71, 60, 30, 35, 55, 0, None, 37)] == [0, 1, 2, 3, 4, 4, 5, 5, 5]
    assert flag_of(636012345) == "LR" and flag_of(244123456) == "NL" and flag_of(99123) == "" and flag_of(970123456) == ""


def test_vessel_board_expiry_cap_snapshot_and_gates():
    b = VesselBoard(ttl=1800, cap=3)
    b.message(pos(636000001, 26.5, 56.3, 12.0, 270, "TANKY"), T)                    # inside the Hormuz box
    b.message(static(636000001, 84), T)
    b.message(pos(244000002, 51.0, 3.0, 0.0, 511), T)                               # no heading: course unusable at rest -> -1
    b.message(pos(412000003, 10.0, 10.0, 102.3, 511), T)                            # speed n/a
    b.message({"MetaData": {"MMSI": 5}, "Message": {"PositionReport": {"Latitude": 200, "Longitude": 0}}}, T)   # garbage ignored
    doc, gates = b.snapshot(T + 60)
    rows = {r[0]: r for r in doc["rows"]}
    assert doc["n"] == 3 and rows[636000001][:7] == [636000001, 56.3, 26.5, 270, 12.0, 0, int(T)]
    assert rows[636000001][7:10] == ["TANKY", "ROTTERDAM", "LR"] and doc["counts"]["tanker"] == 1
    assert rows[244000002][3] == -1 and rows[412000003][4] == -1.0
    assert gates["hormuz"] == {"in_strait": 1, "moving": 1, "tankers": 1} and gates["suez"]["in_strait"] == 0
    for i in range(10):                                                              # the cap keeps the freshest
        b.message(pos(200000000 + i, 1.0, 1.0), T + 100 + i)
    doc, _ = b.snapshot(T + 200)
    assert doc["n"] == 3 and {r[0] for r in doc["rows"]} == {200000009, 200000008, 200000007}
    doc, _ = b.snapshot(T + 100 + 1800 + 100)                                        # all expired after the TTL
    assert doc["n"] == 0 and not b.v and not b.tracks.t and not b.name


def test_dark_and_stopped_tanker_flags_and_trails():
    b = VesselBoard()
    b.message(pos(636000001, 26.5, 56.3, 12.0, 270), T)
    b.message(static(636000001, 80), T)
    b.message(pos(636000002, 26.6, 56.3, 0.0, 10), T + 900)
    b.message(static(636000002, 80), T + 900)
    doc, _ = b.snapshot(T + 900 + flags.DARK_AFTER_S)
    nf = {r[0]: (r[10] if len(r) > 10 else 0) for r in doc["rows"]}
    assert nf[636000001] & 2 and not nf[636000002] & 2        # moving then silent = dark
    assert nf[636000002] & 4                                   # a tanker stopped inside a strait
    for i in range(1, 40):                                     # trails: one point per step, bounded, oldest dropped
        b.message(pos(636000001, 26.5 + i * 0.001, 56.3, 12.0, 270), T + i * flags.TRACK_STEP_S)
    pts = b.tracks.t[636000001]
    assert len(pts) <= flags.TRACK_POINTS * 3
    shard = b.tracks.shard(636000001 % flags.TRACK_SHARDS, flags.TRACK_SHARDS)["636000001"]
    assert len(shard) == len(pts) // 3 * 2


# ── aircraft ──────────────────────────────────────────────────────────────────────────────────
def test_sky_board_merges_mil_and_civil_and_publishes_no_address():
    mil = {"ac": [{"hex": "ae1234", "lat": 44.0, "lon": 33.0, "t": "K35R", "track": 90, "gs": 400, "flight": "QUID12 ", "alt_baro": 30000}]}
    civ = {"ac": [{"hex": "4ca111", "lat": 51.0, "lon": 2.0, "t": "A320", "track": 270, "gs": 450, "flight": "EZY123", "alt_baro": "ground"},
                  {"hex": "ae9999", "lat": 40.0, "lon": 30.0, "t": "F16", "dbFlags": 1, "gs": 500}, {"hex": "x"}]}

    def get(url, *a, **k):
        return json.dumps(mil if url.endswith("/mil") else civ)

    s = SkyBoard()
    got = s.poll(get, T)
    assert got["mil"] == 1 and got["civil"] == 2 * flags.CIVIL_POLLS_PER_CYCLE            # same fixture returned by each hub: ids dedupe
    doc = s.snapshot(T + 10)
    rows = {r[0]: r for r in doc["rows"]}
    assert doc["n"] == 3 and doc["counts"] == {"civil": 1, "military": 2}
    assert rows[aircraft_id("AE1234")][5] == 2 and rows[aircraft_id("ae1234")][7] == "QUID12"      # tanker; callsign trimmed
    assert rows[aircraft_id("ae9999")][5] == 5 and rows[aircraft_id("4ca111")][5] == 0
    assert "ae1234" not in json.dumps(doc).lower()                                           # the ICAO address is never published
    s.snapshot(T + flags.CIVIL_TTL_S + 100)
    assert aircraft_id("4ca111") not in s.a and flags.CIVIL_TTL_S > flags.MIL_TTL_S or len(s.a) == 0   # past the civil TTL civil is gone
    s.snapshot(T + flags.MIL_TTL_S + flags.CIVIL_TTL_S + 1000)
    assert not s.a and not s.tracks.t


def test_sky_board_cap_keeps_military_and_freshest_civil(monkeypatch):
    monkeypatch.setattr(flags, "AIRCRAFT_MAX", 3)
    s = SkyBoard()
    civ = {"ac": [{"hex": f"c{i:05d}", "lat": 1.0, "lon": 1.0} for i in range(5)]}
    s.ingest(json.dumps(civ), T, all_military=False)
    s.ingest(json.dumps({"ac": [{"hex": "m00001", "lat": 2.0, "lon": 2.0}]}), T, all_military=True)
    doc = s.snapshot(T + 1)
    assert doc["n"] == 3 and doc["counts"]["military"] == 1


# ── snapshots ─────────────────────────────────────────────────────────────────────────────────
def test_snapshots_upload_compact_json_with_a_short_cache_header_and_skip_unchanged(monkeypatch):
    monkeypatch.setenv("SUPABASE_URL", "https://x.supabase.co")
    monkeypatch.setenv("SUPABASE_SERVICE_ROLE_KEY", "k")
    sent = []

    def http(method, url, headers, body):
        sent.append((url, headers["Cache-Control"], body))
        return 200

    doc = {"v": 1, "rows": [[1, 2.5, 3.5]]}
    r = snapshots.publish({"vessels": doc, "tracks/v0": {"t": {}}}, local=("vessels",), http=http)
    assert r["assets"] == 2
    assert {u.rsplit("/published-assets/", 1)[1] for u, _, _ in sent} == {"live/vessels.json.gz", "live/tracks/v0.json.gz"}
    assert all(c == flags.SNAPSHOT_CACHE for _, c, _ in sent)
    assert gzip.decompress(next(b for u, _, b in sent if u.endswith("vessels.json.gz"))) == b'{"v":1,"rows":[[1,2.5,3.5]]}'
    assert store.read_doc("vessels") == doc
    assert snapshots.publish({"vessels": doc}, http=http)["skipped"] == 1                  # unchanged: not re-uploaded


def test_build_docs_makes_every_layer_and_the_trail_shards():
    b, s = VesselBoard(), SkyBoard()
    b.message(pos(636000001, 26.5, 56.3), T)
    docs = build_docs(b, s, T + 1, tracks=True)
    assert {"vessels", "aircraft", "summary"} <= set(docs)
    assert sum(k.startswith("tracks/v") for k in docs) == flags.TRACK_SHARDS and sum(k.startswith("tracks/a") for k in docs) == flags.AIR_TRACK_SHARDS
    assert docs["coverage"]["cells"] and docs["coverage"]["deg"] == flags.COVERAGE_DEG
    assert docs["summary"]["gates"]["hormuz"]["in_strait"] == 1 and docs["summary"]["fresh"]["ships"] == docs["vessels"]["as_of"]
    assert store.read_doc("gates_now")["gates"]["hormuz"]["in_strait"] == 1


# ── energy ────────────────────────────────────────────────────────────────────────────────────
def put(series_id, points):
    istore.append(series_id, [Observation(series_id=series_id, period=d, value=v, fetched_at="t", source_url="u") for d, v in points])


def test_energy_gas_storage_against_earlier_years_and_tiles():
    pts = []
    for y, base in ((2022, 60.0), (2023, 80.0), (2024, 90.0), (2025, 70.0), (2026, 50.0)):
        for d in range(0, 100):
            day = date(y, 7, 1).toordinal() + d
            pts.append((date.fromordinal(day).isoformat(), base + d * 0.2))
    put("gas_eu_storage", pts)
    put("px_brent", [("2026-10-08", 80.0), ("2026-10-09", 84.0)])
    put("lng_eu_sendout", [(f"2026-10-{d:02d}", 100.0 + d) for d in range(1, 10)])
    doc = energy.build(NOW)
    gas = doc["gas"]
    assert gas["as_of_day"] == "2026-10-08" and gas["value"] == 69.8 and len(gas["spark"]) == energy.SPARK_DAYS
    assert [y["year"] for y in gas["years"]] == [2025, 2024, 2023, 2022]
    assert gas["band"][-1] == [round(min(y["value"] for y in gas["years"]), 1), round(max(y["value"] for y in gas["years"]), 1)]
    assert doc["tiles"][0]["id"] == "px_brent" and doc["tiles"][0]["change_pct"] == 5.0
    assert doc["lng"]["sendout"]["value"] == 109.0 and doc["credits"]["gas"]["text"] == "Source: GIE AGSI+"
    assert energy.build(NOW) is not None


def test_energy_is_none_without_any_data():
    assert energy.build(NOW) is None


# ── the headline strip ────────────────────────────────────────────────────────────────────────
def ev(**kw):
    base = dict(id="e", feed="f", kind="outage", title="t", lat=1.0, lon=2.0, start="2026-10-11T08:00:00+00:00")
    return LiveEvent(**{**base, **kw})


def srows(sid, done, cur=None):
    rows = [(sid, f"2026-09-{i + 1:02d}", v, False, "n", "u", "k", "r", 0, 0, "s") for i, v in enumerate(done)]
    if cur is not None:
        rows.append((sid, "2026-10-11", cur, True, "n", "u", "k", "r", 0, 0, "s"))
    return rows


def test_outlier_needs_history_and_beats_the_whole_window():
    assert headlines.outlier([5, 5, 5], 50) is None
    h = [10, 11, 9, 10, 12, 10, 11]
    assert headlines.outlier(h, 30) == "high" and headlines.outlier(h, 12) is None and headlines.outlier(h, 2) == "low"
    assert headlines.outlier([0] * 7, 0) is None


def test_headlines_rank_cap_per_layer_and_centre_on_the_thing():
    events = [ev(id="o1", countries=["Iran"], severity="major", lat=32.0, lon=53.0),
              ev(id="o2", countries=["Chad"], severity="notable"),
              ev(id="o3", countries=["Mali"], severity="notable"),
              ev(id="q1", kind="quake", title="M6.8 earthquake, off Fiji", severity="major", lat=-20.0, lon=179.0, data={"magnitude": 6.8}),
              ev(id="f1", kind="fire", title="Strong satellite heat reading in Libya", data={"notable": True, "frp_mw": 812.0}),
              ev(id="old", countries=["Peru"], end="2026-10-10T00:00:00+00:00")]
    rows = (srows("live_fire_ukraine_front", [10, 12, 9, 11, 10, 13, 10], 60)
            + srows("live_ais_hormuz_transits", [100, 102, 98, 101, 99, 100, 60]))
    gates_now = {"gates": {"hormuz": {"in_strait": 12, "moving": 9, "tankers": 4}}}
    out = headlines.compute(events, rows, gates_now, NOW)
    layers = [i["layer"] for i in out]
    assert out[0]["text"] == "Internet down nationwide in Iran since 08:00 UTC" and out[0]["lat"] == 32.0
    assert layers.count("outage") == headlines.PER_LAYER and len(out) <= flags.HEADLINES_MAX            # one of three notables is cut
    assert all(i["id"] != "old" for i in out)
    texts = " | ".join(i["text"] for i in out)
    assert "M6.8 earthquake, off Fiji" in texts and "Fires surging near Eastern Ukraine front: 60 heat readings" in texts
    assert "Strait of Hormuz: 12 ships in the strait now, transits 40% below usual" in texts
    assert [i["score"] for i in out] == sorted((i["score"] for i in out), reverse=True)


def test_headlines_quiet_chokepoint_says_what_is_there_and_nothing_else():
    rows = srows("live_ais_suez_transits", [50, 51, 49, 50, 52, 50, 50])
    out = headlines.compute([], rows, {"gates": {"suez": {"in_strait": 7, "moving": 5, "tankers": 1}}}, NOW)
    assert [i["text"] for i in out] == ["Suez Canal: 7 ships in the strait now (5 moving)"]
    assert headlines.compute([], rows, None, NOW) == []


def test_summary_build_carries_freshness_gates_and_fires_meta():
    store.record_status("ioda", last_ok="2026-10-11T09:55:00+00:00")
    store.write_doc("fires_meta", {"as_of": "x", "detections": 5, "occupied": 3, "extra": 1})
    store.write_doc("gates_now", {"as_of": "2026-10-11T09:59:00+00:00", "gates": {"hormuz": {"in_strait": 3, "moving": 2, "tankers": 1}}})
    s = headlines.build(NOW, rows=srows("live_ais_hormuz_transits", [1, 2, 3], 4) + srows("live_ais_hormuz_tanker_transits", [], 2))
    assert s["fresh"]["outage"] == "2026-10-11T09:55:00+00:00" and s["fresh"]["ships"] == "2026-10-11T09:59:00+00:00"
    g = s["gates"]["hormuz"]
    assert g["in_strait"] == 3 and g["transits_today"] == 4 and g["tanker_transits_today"] == 2 and g["label"] == "Strait of Hormuz"
    assert s["fires"] == {"as_of": "x", "detections": 5, "occupied": 3, "scope": "world"}
