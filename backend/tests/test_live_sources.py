"""Live sources: OpenSky (parse, merge into the sky board, credit-aware cadence), the AIS decoder, Digitraffic, the vessel board's
multi-source merge, the static-type memory and the receiver-coverage grid. Offline: every network call is injected."""

from __future__ import annotations

import json
from datetime import datetime, timezone

import pytest

from algent_backend.live import flags, store
from algent_backend.live.ais_memory import Coverage, StaticMemory
from algent_backend.live.board import VesselBoard
from algent_backend.live.classify import aircraft_id
from algent_backend.live.ingest import digitraffic, kystverket, nmea, opensky
from algent_backend.live.sky import SkyBoard

T = datetime(2026, 10, 11, 10, 0, tzinfo=timezone.utc).timestamp()


@pytest.fixture(autouse=True)
def _env(tmp_path, monkeypatch):
    monkeypatch.setenv("ALGENT_LIVE_STORE", str(tmp_path / "live"))
    monkeypatch.delenv(opensky.ID_ENV, raising=False)
    monkeypatch.delenv(opensky.SECRET_ENV, raising=False)


# ── OpenSky ───────────────────────────────────────────────────────────────────────────────────
def state(icao="a1b2c3", call="UAL123  ", t=T - 5, lon=-104.7, lat=39.85, alt=10000.0, ground=False, vel=230.0, track=270.0):
    return [icao, call, "United States", t, t, lon, lat, alt, ground, vel, track, 0, None, alt, "1200", False, 0]


def test_opensky_state_parses_units_and_drops_unusable_rows():
    icao, rec = opensky.parse_state(state(), T)
    assert icao == "a1b2c3" and rec[:2] == [39.85, -104.7] and rec[6] == "UAL123"
    assert round(rec[3]) == 447 and rec[8] == 32808 and rec[5] == 0 and rec[7] == ""      # m/s -> kn, m -> ft, civil, no type code
    assert opensky.parse_state(state(ground=True), T)[1][8] == 0                          # on the ground
    assert opensky.parse_state(state(t=T - flags.OPENSKY_MAX_AGE_S - 1), T) is None        # stale
    assert opensky.parse_state(state(lat=None), T) is None and opensky.parse_state([], T) is None
    assert opensky.parse_state(state(alt=None), T)[1][8] == -1


def test_sky_merges_opensky_with_adsb_freshest_wins_and_keeps_military_class():
    s = SkyBoard()
    mil = {"ac": [{"hex": "ae1234", "lat": 44.0, "lon": 33.0, "t": "K35R", "track": 90, "gs": 400, "flight": "QUID12", "alt_baro": 30000}]}
    s.ingest(json.dumps(mil), T - 30, all_military=True)
    # OpenSky saw the same aircraft later: the position moves on, the military class and type code stay.
    n = s.ingest_opensky([state("ae1234", "QUID12", t=T - 2, lat=44.1, lon=33.2), state("4ca111", lat=51.0, lon=2.0),
                          state("zz", t=T - 500)], T, ttl=300)
    assert n == 2
    doc = s.snapshot(T + 1)
    rows = {r[0]: r for r in doc["rows"]}
    k = rows[aircraft_id("ae1234")]
    assert k[5] == 2 and k[2] == 44.1 and k[7] == "QUID12" and k[8] == "K35R"
    assert rows[aircraft_id("4ca111")][5] == 0 and doc["counts"] == {"civil": 1, "military": 1}
    # an OLDER sighting never displaces a fresher one
    assert s.ingest_opensky([state("ae1234", t=T - 100, lat=1.0, lon=1.0)], T, ttl=300) == 0
    # OpenSky records live for their own ttl, not the 8-minute adsb.lol one
    s.snapshot(T + 200)
    assert aircraft_id("4ca111") in s.a
    s.snapshot(T + 400)
    assert aircraft_id("4ca111") not in s.a


def test_opensky_cadence_follows_the_credit_budget_and_the_tier(monkeypatch):
    anon = opensky.OpenSky(http=lambda *a: (200, {}, b"{}"))
    assert not anon.authenticated and anon.interval == flags.OPENSKY_INTERVAL_ANON_S
    assert 86400 / flags.OPENSKY_INTERVAL_ANON_S * 4 <= 400                      # anonymous: 400 credits a day, 4 per global call
    monkeypatch.setenv(opensky.ID_ENV, "id")
    monkeypatch.setenv(opensky.SECRET_ENV, "secret")
    assert 86400 / flags.OPENSKY_INTERVAL_AUTH_S * 4 <= 4000                     # account: 4 000 a day
    calls = []

    def http(method, url, headers, form):
        calls.append((method, url, form))
        if url == opensky.TOKEN_URL:
            return 200, {}, json.dumps({"access_token": "tok", "expires_in": 1800}).encode()
        assert headers["Authorization"] == "Bearer tok"
        return 200, {"x-rate-limit-remaining": "10"}, json.dumps({"states": [state()]}).encode()

    cli = opensky.OpenSky(http=http)
    assert cli.authenticated and len(cli.fetch()) == 1 and len(cli.fetch()) == 1
    assert [c[0] for c in calls] == ["POST", "GET", "GET"] and calls[0][2]["grant_type"] == "client_credentials"   # one token for both
    assert cli.remaining == 10 and cli.interval == 2 * flags.OPENSKY_INTERVAL_AUTH_S                                 # credits low: slow down


def test_opensky_429_names_the_wait():
    cli = opensky.OpenSky(http=lambda *a: (429, {"x-rate-limit-retry-after-seconds": "812"}, b""))
    with pytest.raises(RuntimeError, match="HTTP 429 retry-after 812"):
        cli.fetch()


# ── AIS decoding ──────────────────────────────────────────────────────────────────────────────
def armour(bits: str) -> tuple[str, int]:
    pad = (-len(bits)) % 6
    bits += "0" * pad
    out = ""
    for i in range(0, len(bits), 6):
        v = int(bits[i:i + 6], 2)
        out += chr(v + 48 if v < 40 else v + 56)
    return out, pad


def field(v: int, width: int) -> str:
    return format(v & ((1 << width) - 1), f"0{width}b")


def text(s: str, chars: int) -> str:
    return "".join(field(ord(c) - 64 if ord(c) >= 64 else ord(c), 6) for c in s.ljust(chars, "@"))


def sentence(payload: str, pad: int, total=1, num=1, seq="", ch="A") -> str:
    return f"!AIVDM,{total},{num},{seq},{ch},{payload},{pad}*00"


def class_a(mmsi, lat, lon, sog=12.3, cog=45.6, hdg=47):
    b = field(1, 6) + field(0, 2) + field(mmsi, 30) + field(0, 4) + field(0, 8) + field(round(sog * 10), 10) + field(0, 1) \
        + field(round(lon * 600000), 28) + field(round(lat * 600000), 27) + field(round(cog * 10), 12) + field(hdg, 9) + "0" * 40
    return armour(b)


def test_decoder_class_a_position_and_known_real_sentence():
    payload, pad = class_a(244123456, 51.9, 4.45)
    msg = nmea.Decoder().feed("\\s:2573,c:1700000000*00\\" + sentence(payload, pad))      # a tag block before the sentence is ignored
    assert msg["kind"] == "pos" and msg["mmsi"] == 244123456
    assert abs(msg["lat"] - 51.9) < 1e-4 and abs(msg["lon"] - 4.45) < 1e-4 and msg["sog"] == 12.3 and msg["cog"] == 45.6 and msg["heading"] == 47
    real = nmea.Decoder().feed("!AIVDM,1,1,,B,15M67FC000G?ufbE`FepT@3n00Sa,0*5C")          # widely published sample sentence (San Francisco Bay)
    assert real["mmsi"] == 366053209 and 37 < real["lat"] < 38 and -123 < real["lon"] < -122


def test_decoder_not_available_values_and_garbage():
    payload, pad = class_a(244123456, 91.0, 181.0)
    assert nmea.Decoder().feed(sentence(payload, pad)) is None                               # 91 / 181 = no position
    payload, pad = class_a(244123456, 10.0, 10.0, sog=102.3, cog=360.0, hdg=511)
    msg = nmea.Decoder().feed(sentence(payload, pad))
    assert msg["sog"] is None and msg["cog"] is None and msg["heading"] is None
    d = nmea.Decoder()
    assert d.feed("") is None and d.feed("!AIVDM,1,1,,A,,0*00") is None and d.feed("$GPGGA,1,2*00") is None and d.feed("!AIVDM,x") is None


def test_decoder_static_multipart_and_class_b_parts():
    b = field(5, 6) + field(0, 2) + field(636012345, 30) + "0" * 74 + text("TEST TANKER", 20) + field(84, 8) + "0" * 62 + text("ROTTERDAM", 20) + "0" * 10
    payload, pad = armour(b)
    cut = 60
    d = nmea.Decoder()
    assert d.feed(sentence(payload[:cut], 0, 2, 1, "3")) is None
    msg = d.feed(sentence(payload[cut:], pad, 2, 2, "3"))
    assert msg == {"kind": "static", "mmsi": 636012345, "type": 84, "name": "TEST TANKER", "dest": "ROTTERDAM"}
    pa, pada = armour(field(24, 6) + field(0, 2) + field(244999999, 30) + field(0, 2) + text("SAILOR", 20) + "0" * 8)
    pb, padb = armour(field(24, 6) + field(0, 2) + field(244999999, 30) + field(1, 2) + field(37, 8) + "0" * 60)
    assert nmea.Decoder().feed(sentence(pa, pada))["name"] == "SAILOR"
    assert nmea.Decoder().feed(sentence(pb, padb))["type"] == 37


def test_kystverket_message_lands_on_the_board():
    board = VesselBoard()
    payload, pad = class_a(257123456, 69.65, 18.95)
    assert kystverket.apply(board, nmea.Decoder().feed(sentence(payload, pad)), T) is True
    assert board.v[257123456][:2] == pytest.approx([69.65, 18.95], abs=1e-4)
    assert kystverket.apply(board, {"kind": "static", "mmsi": 257123456, "type": 70, "name": "FJORD", "dest": ""}, T) is False
    assert board.static.get(257123456)[:2] == [70, "FJORD"]


# ── Digitraffic ───────────────────────────────────────────────────────────────────────────────
def test_digitraffic_parse_and_merge_by_mmsi():
    locs = json.dumps({"features": [
        {"mmsi": 230111000, "geometry": {"coordinates": [24.9, 60.15]}, "properties": {"sog": 11.5, "cog": 200.0, "heading": 511, "timestampExternal": int((T - 20) * 1000)}},
        {"mmsi": 0, "geometry": {"coordinates": [1, 2]}, "properties": {}}]})
    ves = json.dumps([{"mmsi": 230111000, "name": "SILJA STAR", "shipType": 60, "destination": "STOCKHOLM"}, {"nope": 1}])
    board = VesselBoard()
    assert digitraffic.apply(board, digitraffic.parse_locations(locs), digitraffic.parse_vessels(ves), T) == 1
    doc, _ = board.snapshot(T + 1)
    row = doc["rows"][0]
    assert row[0] == 230111000 and row[3] == 200 and row[4] == 11.5 and row[5] == 2            # heading falls back to course; passenger
    assert row[7:10] == ["SILJA STAR", "STOCKHOLM", "FI"]


# ── the vessel board across sources ──────────────────────────────────────────────────────────────
def test_board_report_freshest_wins_and_type_zero_never_erases_a_known_type():
    b = VesselBoard()
    assert b.report(636000001, 10.0, 20.0, T, sog=5, heading=90)
    assert b.report(636000001, 11.0, 21.0, T - 60, sog=5, heading=90) is False            # older report from a slower source
    assert b.v[636000001][:2] == [10.0, 20.0]
    b.static.put(636000001, 84, "TANKY", "ROTTERDAM", T)
    b.static.put(636000001, 0, None, None, T + 1)                                          # a Class B part A: type 0 = "not available"
    assert b.static.get(636000001)[:3] == [84, "TANKY", "ROTTERDAM"]
    b.message({"MetaData": {"MMSI": 5, "latitude": 1.0, "longitude": 2.0, "ShipName": "EXT"},
               "Message": {"ExtendedClassBPositionReport": {"UserID": 5, "Sog": 6.0, "Cog": 12.0, "TrueHeading": 511, "Type": 37}}}, T)
    assert b.static.get(5)[0] == 37 and b.v[5][2] == 12.0                                  # the type rides on the extended Class B report
    b.message({"MetaData": {"MMSI": 6, "latitude": -40.0, "longitude": 150.0}, "Message": {"LongRangeAisBroadcastMessage": {"UserID": 6, "Sog": 14, "Cog": 80}}}, T)
    assert 6 in b.v


def test_static_memory_survives_a_restart_and_is_bounded(tmp_path, monkeypatch):
    mem = StaticMemory()
    mem.put(1, 84, "A", "X", T)
    mem.put(2, 70, "B", "", T - flags.STATIC_KEEP_S - 10)
    path = tmp_path / "s.json"
    StaticMemory.write(path, mem.m)
    back = StaticMemory.load(path)
    assert back.get(1) == [84, "A", "X", T]
    back.prune(T)
    assert back.get(2) is None and back.get(1) is not None                                  # expired after the keep time
    monkeypatch.setattr(flags, "STATIC_MAX", 2)
    for i in range(5):
        back.put(100 + i, 30, "", "", T + i)
    back.prune(T + 10)
    assert set(back.m) == {104, 103}
    assert StaticMemory.load(tmp_path / "missing.json").m == {}
    (tmp_path / "bad.json").write_text("{not json")
    assert StaticMemory.load(tmp_path / "bad.json").m == {}
    board = VesselBoard(static=back)                                                         # a fresh board knows the types at once
    board.report(104, 1.0, 1.0, T + 11)
    doc, _ = board.snapshot(T + 12)
    assert doc["rows"][0][5] == 3                                                             # fishing, from memory


def test_coverage_grid_counts_cells_heard_in_the_last_day(tmp_path):
    c = Coverage()
    c.hear(51.9, 4.45, T)
    c.hear(51.2, 4.9, T)                                                                      # same 1-degree cell
    c.hear(-33.9, 18.4, T - flags.COVERAGE_KEEP_S - 5)                                        # heard, but more than a day ago
    doc = c.document("t", T)
    assert doc["cells"] == [Coverage.cell(51.9, 4.45)] and doc["deg"] == 1 and doc["hours"] == 24
    row, col = divmod(doc["cells"][0], 360)
    assert (row - 90, col - 180) == (51, 4)
    Coverage.write(tmp_path / "c.json", c.seen)
    assert Coverage.load(tmp_path / "c.json").seen.keys() == c.seen.keys()
    board = VesselBoard(coverage=Coverage())
    board.report(1, 10.5, 20.5, T)
    assert board.coverage.document("t", T)["cells"] == [Coverage.cell(10.5, 20.5)]
