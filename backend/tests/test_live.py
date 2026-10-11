"""Live feeds: parsers on captured-shape payloads, the AIS gate counter, the running-day store, the runner, the desk block."""

from __future__ import annotations

import json
from datetime import date, datetime, timezone

import pytest

from algent_backend.instruments import store as istore
from algent_backend.instruments.catalog import get_series
from algent_backend.instruments.contracts import Observation
from algent_backend.live import desk, flags, places, runner, store
from algent_backend.live.contracts import Ctx, NeedsKey, Stat
from algent_backend.live.feeds import adsb, firms, ioda, usgs
from algent_backend.live.feeds.ais import GateCounter

NOW = datetime(2026, 10, 11, 10, 0, tzinfo=timezone.utc)


@pytest.fixture(autouse=True)
def _env(tmp_path, monkeypatch):
    monkeypatch.setenv("ALGENT_INSTRUMENTS_STORE", str(tmp_path / "istore"))
    monkeypatch.setenv("ALGENT_LIVE_STORE", str(tmp_path / "live"))
    monkeypatch.delenv("DATABASE_URL", raising=False)
    monkeypatch.setattr(places, "by_code", lambda code: None)
    monkeypatch.setattr(places, "country_at", lambda lat, lon: "Fiji" if lat < -20 else None)


def ctx(payload: str = "", key: str = "") -> Ctx:
    return Ctx(get=lambda *a, **k: payload, now=NOW, key=key)


def test_ioda_merges_measurements_per_country_and_marks_ongoing():
    t = int(NOW.timestamp())
    rows = [{"location": "country/IR", "start": t - 7200, "duration": 7200, "datasource": "bgp", "score": 10.0, "location_name": "Iran"},
            {"location": "country/IR", "start": t - 3600, "duration": 3600, "datasource": "ping-slash24", "score": 30.0, "location_name": "Iran"},
            {"location": "country/TN", "start": t - 90000, "duration": 40000, "datasource": "bgp", "score": 5.0, "location_name": "Tunisia"}]
    events = ioda.parse(json.dumps({"data": rows}), NOW)
    iran = next(e for e in events if e.countries == ["Iran"])
    assert iran.end is None and iran.severity == "major" and iran.source_url.endswith("/country/IR")
    assert iran.data["measurements"] == ["bgp", "ping-slash24"]
    tunisia = next(e for e in events if e.countries == ["Tunisia"])
    assert tunisia.end is not None and tunisia.severity == "info" and "(ended)" in tunisia.title
    assert events[0] is iran                                  # ongoing first


def test_usgs_severity_and_country():
    doc = {"features": [
        {"id": "a", "properties": {"mag": 7.7, "place": "south of the Fiji Islands", "time": 1791703732878, "url": "https://x/a", "tsunami": 1},
         "geometry": {"coordinates": [179.9, -23.6, 546.0]}},
        {"id": "b", "properties": {"mag": 4.6, "place": "somewhere", "time": 1791703732878, "url": "https://x/b", "alert": None},
         "geometry": {"coordinates": [10.0, 40.0, 10.0]}}]}
    events = usgs.parse(json.dumps(doc))
    assert [e.severity for e in events] == ["major", "info"] and events[0].countries == ["Fiji"] and events[1].countries == []
    assert events[0].source_url == "https://x/a" and "tsunami" in events[0].detail


def test_adsb_region_counts_roles_and_stats():
    planes = [{"lat": 44.0, "lon": 33.0, "t": "RQ4"}, {"lat": 43.5, "lon": 34.0, "t": "C17"}, {"lat": 10.0, "lon": 10.0, "t": "K35R"},
              {"lat": 44.2, "lon": 30.0, "t": "K35R"}, {"t": "C17"}]
    res = adsb.parse(json.dumps({"ac": planes}), ctx())
    ev = next(e for e in res.events if e.data["region"] == "black_sea")
    assert ev.data["count"] == 3 and ev.data["roles"] == {"tanker": 1, "surveillance": 1, "airlift": 1}
    stats = {s.series_id: s.value for s in res.stats}
    assert stats["live_mil_black_sea"] == 3 and stats["live_mil_black_sea_support"] == 2 and stats["live_mil_baltic"] == 0
    assert "tail" not in ev.detail.lower() and "minimum" in ev.detail


def test_firms_needs_key_then_clusters():
    with pytest.raises(NeedsKey, match="ALGENT_FIRMS_KEY.*firms.modaps.eosdis.nasa.gov"):
        firms.fetch(ctx())
    csv_text = ("latitude,longitude,acq_date,acq_time,confidence,frp\n"
                "48.01,37.01,2026-10-11,0930,h,20.5\n48.02,37.02,2026-10-11,0930,n,5\n48.5,38.5,2026-10-11,0930,l,50\n")
    res = firms.fetch(ctx(csv_text, key="K"))
    assert res.events and res.events[0].data["hotspots"] == 2
    stats = {s.series_id: s.value for s in res.stats}
    assert stats["live_fire_ukraine_front"] == 2                # the low-confidence row is dropped


def gate_msgs(mmsi, points):
    return [{"MetaData": {"MMSI": mmsi, "latitude": la, "longitude": lo}, "Message": {"PositionReport": {"UserID": mmsi}}} for la, lo in points]


def test_gate_counter_counts_unique_crossings_and_tankers():
    c = GateCounter()
    # Hormuz gate is the meridian 56.45 between lat 25.9 and 27.0
    for m in gate_msgs(1, [(26.5, 56.2), (26.5, 56.7), (26.5, 56.2), (26.5, 56.7)]):    # crosses three times: one ship
        c.message(m, 1000.0, "2026-10-11")
    for m in gate_msgs(2, [(26.5, 56.2), (26.5, 56.3)]):                                  # never crosses
        c.message(m, 1000.0, "2026-10-11")
    for m in gate_msgs(3, [(26.5, 56.7), (26.5, 56.2)]):
        c.message(m, 1000.0, "2026-10-11")
    c.message({"MetaData": {"MMSI": 3}, "Message": {"ShipStaticData": {"UserID": 3, "Type": 84}}}, 1000.0, "2026-10-11")
    stats = {s.series_id: s.value for s in c.stats()}
    assert stats["live_ais_hormuz_transits"] == 2 and stats["live_ais_hormuz_tanker_transits"] == 1
    assert stats["live_ais_suez_transits"] == 0
    c2 = GateCounter.from_json(json.loads(json.dumps(c.to_json())))
    assert {s.series_id: s.value for s in c2.stats()} == stats
    c.message(gate_msgs(9, [(26.5, 56.2)])[0], 2000.0, "2026-10-12")
    assert c.crossed["hormuz"] == set()                                                  # a new UTC day restarts the counts


def test_running_day_completes_only_after_midnight():
    sid = "live_mil_baltic"
    store.apply_stats([Stat(series_id=sid, value=3)], date(2026, 10, 10))
    store.apply_stats([Stat(series_id=sid, value=5), Stat(series_id=sid, value=4)], date(2026, 10, 10))
    assert istore.history(sid) == []                                                     # the open day is not an observation
    assert store.running()[sid]["value"] == 5                                            # day maximum
    out = store.apply_stats([Stat(series_id=sid, value=1)], date(2026, 10, 11))
    assert out["completed"] == 1
    assert [(o.period, o.value) for o in istore.history(sid)] == [("2026-10-10", 5.0)]


def test_runner_isolates_feeds_and_keeps_snapshot_on_failure():
    t = int(NOW.timestamp())
    ioda_doc = json.dumps({"data": [{"location": "country/IR", "start": t - 100, "duration": 100, "datasource": "bgp", "score": 1,
                                     "location_name": "Iran"}]})

    def get(url, params=None, **kw):
        if "ioda" in url:
            return ioda_doc
        raise RuntimeError("down")

    out = runner.run(["ioda", "usgs", "firms"], get=get, now=NOW)
    status = {r["feed"]: r["status"] for r in out["feeds"]}
    assert status == {"ioda": "ok", "usgs": "error", "firms": "needs_key"}
    assert len(store.read_events("ioda")) == 1
    runner.run(["ioda"], get=lambda *a, **k: (_ for _ in ()).throw(RuntimeError("down")), now=NOW)
    assert len(store.read_events("ioda")) == 1                                           # failed run did not blank the map
    rows = {r["feed"]: r for r in runner.doctor_rows()}
    assert rows["firms"]["needs"].startswith("needs ALGENT_FIRMS_KEY") and rows["ioda"]["error"]
    assert rows["ais"]["service"] and rows["usgs"]["keyless"]
    with pytest.raises(KeyError):
        runner.run(["ais"], get=lambda *a, **k: "")


def test_desk_block_cites_source_for_matching_countries():
    t = int(NOW.timestamp())
    runner.run(["ioda"], get=lambda *a, **k: json.dumps({"data": [
        {"location": "country/IN", "start": t - 100, "duration": 100, "datasource": "bgp", "score": 1, "location_name": "India"}]}), now=NOW)
    text, urls, n = desk.block({"India"})
    assert n == 1 and "LIVE EVENTS" in text and "ioda.inetintel.cc.gatech.edu/country/IN" in text and urls
    assert desk.block({"Chad"}) == ("", set(), 0)


def test_live_series_are_in_the_catalog_and_tagged_for_the_numbers_panel():
    s = get_series("live_ais_hormuz_transits")
    assert "chokepoint" in s.tags and "hormuz" in s.tags and s.fetcher == "live" and s.cadence == "daily"
    from algent_backend.instruments.collect import collect

    istore.append(s.id, [Observation(series_id=s.id, period="2026-10-10", value=3, fetched_at="t", source_url="u")])
    rep = collect(["live_ais_hormuz_transits"])
    assert rep["ok"] == 1                                                                # the live provider is a quiet no-op


def test_doctor_reports_missing_keys_and_never_ran(monkeypatch):
    from algent_backend.ops import doctor

    monkeypatch.delenv("ALGENT_FIRMS_KEY", raising=False)
    checks = doctor.check_live({})
    assert "free registration" in checks["live:firms"]["detail"] and checks["live:ioda"]["status"] == "warn"
    assert flags.CADENCE_MINUTES.keys() == {"ioda", "usgs", "adsb", "firms"}
