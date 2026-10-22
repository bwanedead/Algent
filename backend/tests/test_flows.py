"""Flows: ship class hints, the lane network, the lane tracker (synthetic tracks -> hops -> corridor counts), rates and anomalies, the
Comtrade parsers and trade refresh (fixtures, no network), the published document and its upload."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

import pytest

from algent_backend.flows import backfill, document, flags, network, publish, rates, store
from algent_backend.flows.classes import flow_class
from algent_backend.flows.tracker import LaneTracker, day_of
from algent_backend.flows.trade import comtrade, refresh

FIXTURES = Path(__file__).parent / "fixtures"
H = 3600.0
T0 = datetime(2026, 10, 1, 0, 0, tzinfo=timezone.utc).timestamp()


@pytest.fixture(autouse=True)
def _store(tmp_path, monkeypatch):
    monkeypatch.setenv("ALGENT_LIVE_STORE", str(tmp_path / "live"))


def at(pid: str) -> tuple[float, float]:
    p = network.BY_ID[pid]
    return p.lat, p.lon


def sail(t: LaneTracker, mmsi: int, stops: list[tuple[str, float]], cls: str = "tanker") -> int:
    """Observe a ship at the centre of each place at the given hour offsets; returns the hops counted."""
    return sum(t.observe(mmsi, *at(pid), T0 + hrs * H, lambda: cls) for pid, hrs in stops)


# ── classes ───────────────────────────────────────────────────────────────────────────────────
def test_ship_type_and_name_give_the_flow_class():
    assert flow_class(80, "FRONT ALTAIR") == "tanker"
    assert flow_class(84, "AL NUAMAN LNG") == "lng"
    assert flow_class(70, "MAERSK ESSEX") == "container"
    assert flow_class(79, "STAR BULK PIONEER") == "bulk"
    assert flow_class(70, "NORDIC SPIRIT") == "cargo"
    assert flow_class(60, "SILJA SERENADE") is None          # passenger: not a trade flow
    assert flow_class(None, "MAERSK X") is None              # nothing is guessed from a name alone


# ── the network ───────────────────────────────────────────────────────────────────────────────
def test_every_place_sits_on_the_one_lane_network_and_finds_itself():
    for p in network.PLACES:
        assert network.place_at(p.lat, p.lon) in (p.id, *[q.id for q in network.PLACES if q.kind == "chokepoint"]), p.id
        assert network.route("persian_gulf", p.id) is not None, f"{p.id} is not connected"
    assert network.place_at(0.0, -30.0) is None              # mid-Atlantic: nobody listens there


def test_a_chokepoint_wins_over_the_region_around_it():
    assert network.place_at(26.5, 56.5) == "hormuz"
    assert network.place_at(27.0, 51.0) == "persian_gulf"


def test_route_follows_the_sea_not_the_straight_line():
    path, km = network.route("persian_gulf", "east_med")
    assert path == ("persian_gulf", "hormuz", "gulf_of_oman", "gulf_of_aden", "bab_el_mandeb", "red_sea", "suez", "east_med")
    assert 5000 < km < 9000
    line = network.lane_line("suez", "red_sea")
    assert line[0] == at("suez") and line[-1] == at("red_sea")        # oriented as asked
    assert network.lane_line("red_sea", "suez") == line[::-1]


# ── the tracker ───────────────────────────────────────────────────────────────────────────────
def test_a_ship_crossing_places_makes_observed_hops_on_each_lane():
    t = LaneTracker()
    n = sail(t, 1, [("persian_gulf", 0), ("hormuz", 12), ("gulf_of_oman", 20)])
    assert n == 2
    lanes = t.days[day_of(T0 + 20 * H)]["lanes"]
    assert lanes["persian_gulf>hormuz"]["tanker"] == [1, 0]
    assert lanes["hormuz>gulf_of_oman"]["tanker"] == [1, 0]
    assert t.samples["persian_gulf>hormuz"] == [12.0]                 # the short sample behind a lane's transit time


def test_a_hop_over_unheard_water_counts_every_lane_it_must_have_crossed_as_inferred():
    t = LaneTracker()
    assert sail(t, 2, [("gulf_of_oman", 0), ("suez", 120)]) == 1      # four lanes in five days: plausible
    lanes = t.days[day_of(T0 + 120 * H)]["lanes"]
    assert set(lanes) == {"gulf_of_oman>gulf_of_aden", "gulf_of_aden>bab_el_mandeb", "bab_el_mandeb>red_sea", "red_sea>suez"}
    assert all(by["tanker"] == [0, 1] for by in lanes.values())


def test_the_place_entered_gets_a_visit_per_class():
    t = LaneTracker()
    sail(t, 1, [("hormuz", 0)], "tanker")
    sail(t, 2, [("hormuz", 1)], "bulk")
    assert t.days[day_of(T0)]["visits"]["hormuz"] == {"tanker": 1, "bulk": 1}


def test_impossible_speeds_and_ancient_hops_are_not_counted():
    t = LaneTracker()
    assert sail(t, 3, [("persian_gulf", 0), ("hormuz", 0.2)]) == 0                       # ~600 km in 12 minutes
    assert sail(t, 4, [("persian_gulf", 0), ("hormuz", 24 * (flags.HOP_MAX_DAYS + 2))]) == 0   # a different voyage
    assert not any(v["lanes"] for v in t.days.values())


def test_coming_straight_back_is_one_visit_not_two_hops():
    t = LaneTracker()
    assert sail(t, 5, [("persian_gulf", 0), ("hormuz", 14), ("persian_gulf", 16)]) == 1
    assert "hormuz>persian_gulf" not in t.days[day_of(T0 + 16 * H)]["lanes"]


def test_ships_that_are_not_trade_carriers_and_stale_positions_are_ignored():
    t = LaneTracker()
    assert t.observe(9, *at("hormuz"), T0, lambda: None) is False
    assert 9 not in t.last
    sail(t, 6, [("hormuz", 5)])
    assert t.observe(6, *at("persian_gulf"), T0, lambda: "tanker") is False              # older than what we know
    assert t.last[6][0] == "hormuz"


def test_a_ship_in_open_water_leaves_its_last_place_untouched():
    t = LaneTracker()
    sail(t, 7, [("hormuz", 0)])
    assert t.observe(7, 0.0, -30.0, T0 + H, lambda: "tanker") is False
    assert t.last[7][0] == "hormuz"


class FakeBoard:
    def __init__(self, ships):
        self.v = {m: [lat, lon, 0.0, 12.0, ts] for m, (lat, lon, ts) in ships.items()}
        self.static = type("S", (), {"get": lambda self, m: [80, "TANKER ONE", "", 0.0]})()
        self.name = {}


def test_cycle_scans_the_board_when_due_and_credits_the_time_watched():
    t = LaneTracker()
    now = T0 + 20 * H
    b = FakeBoard({1: (*at("persian_gulf"), T0)})
    assert t.cycle(b, T0)["tracked"] == 1
    b.v[1] = [*at("hormuz"), 0.0, 12.0, T0 + 10 * H]
    assert t.cycle(b, T0 + 100) is None                                       # not due yet
    assert t.cycle(b, T0 + flags.CYCLE_SECONDS)["hops"] == 1
    assert t.days[day_of(T0)]["secs"] == flags.CYCLE_SECONDS
    assert now > T0


def test_state_round_trips_through_disk_as_aggregates_only(tmp_path):
    t = LaneTracker()
    sail(t, 1, [("persian_gulf", 0), ("hormuz", 14)])
    LaneTracker.write(t.snapshot(T0))
    back = LaneTracker.load()
    assert back.last == t.last and back.days == t.days and back.samples == t.samples
    assert all(isinstance(k, str) for d in back.days.values() for k in d["lanes"])        # no vessel ids in the aggregates


def test_old_state_and_old_days_are_dropped():
    t = LaneTracker()
    sail(t, 1, [("hormuz", 0)])
    for i in range(flags.DAY_KEEP + 5):
        t.days[f"2026-01-{i:03d}"] = {"secs": 0.0, "lanes": {}, "visits": {}}
    t.prune(T0 + (flags.STATE_KEEP_DAYS + 1) * 86400)
    assert t.last == {} and len(t.days) == flags.DAY_KEEP


def test_backfill_replays_profile_samples_into_an_empty_tracker_only():
    from algent_backend.maritime.profile import Profile, ProfileBook

    book = ProfileBook()
    p = book.profiles[200000001] = Profile(200000001, T0)
    p.name, p.ship_type = "FRONT ALTAIR", 80
    for pid, hrs in (("persian_gulf", 0), ("hormuz", 12), ("gulf_of_oman", 20)):
        lat, lon = at(pid)
        p.samples.extend((int(T0 + hrs * H), round(lat * 10000), round(lon * 10000), 120))
    t = LaneTracker()
    out = backfill.from_book(book, t)
    assert out["vessels"] == 1 and out["hops"] == 2 and (out["from"], out["to"]) == (day_of(T0), day_of(T0))
    assert t.days[day_of(T0)]["secs"] == pytest.approx(20 * H)
    assert "skipped" in backfill.from_book(book, t)               # a second replay would count the same crossings twice


# ── rates and anomalies ───────────────────────────────────────────────────────────────────────
def day(secs, visits=None, lanes=None):
    return {"secs": secs, "visits": visits or {}, "lanes": lanes or {}}


def test_rates_divide_by_the_time_actually_watched():
    days = {"2026-10-01": day(86400, lanes={"a>b": {"tanker": [10, 0]}}), "2026-10-02": day(43200, lanes={"a>b": {"tanker": [5, 5]}})}
    now = datetime(2026, 10, 2, 12, tzinfo=timezone.utc).timestamp()
    r = rates.lane_rates(days, now, 7)["a>b"]
    assert r["by"]["tanker"] == pytest.approx(20 * 86400 / (86400 + 43200), abs=0.01)     # 20 hops in 1.5 days
    assert r["n"] == 20 and r["inf"] == 5
    assert rates.lane_rates({}, now, 7) == {}


def _history(n, per_day, last):
    days = {f"2026-10-{d:02d}": day(86400, visits={"hormuz": {"tanker": per_day + (d % 3)}}) for d in range(1, n + 1)}
    days[f"2026-10-{n + 1:02d}"] = day(86400, visits={"hormuz": {"tanker": last}})
    return days


def test_a_place_far_outside_its_own_normal_is_flagged_with_direction():
    now = datetime(2026, 10, 12, 6, tzinfo=timezone.utc).timestamp()
    low = rates.anomalies(_history(10, 40, 3), now)["hormuz"]
    assert low["dir"] == "below" and low["z"] < -3.5 and low["usual"] == pytest.approx(41, abs=1.5)
    assert rates.anomalies(_history(10, 40, 41), now)["hormuz"]["dir"] is None
    assert rates.anomalies(_history(10, 40, 120), now)["hormuz"]["dir"] == "above"


def test_a_place_with_too_little_history_is_not_scored_and_unwatched_days_do_not_teach_zeros():
    now = datetime(2026, 10, 12, 6, tzinfo=timezone.utc).timestamp()
    assert rates.anomalies(_history(3, 40, 1), now) == {}
    days = _history(10, 40, 40)
    days["2026-10-05"] = day(3600)                                            # the service was down: not watched, not a zero
    assert rates.anomalies(days, now)["hormuz"]["dir"] is None


# ── trade: Comtrade parsers and the refresh ───────────────────────────────────────────────────
def fixture(name):
    return (FIXTURES / name).read_text(encoding="utf-8")


def test_comtrade_rows_become_partner_flows_without_the_world_total_or_unplaceable_partners():
    flows = comtrade.parse(fixture("flows_comtrade_wheat_us.json"), "US")
    assert {f.dst for f in flows} == {"MX", "PH", "JP", "TW"}              # World (0) and "Areas, nes" (899) dropped; 490 is Taiwan
    mx = next(f for f in flows if f.dst == "MX")
    assert (mx.src, mx.period, mx.usd, mx.kg) == ("US", "2024", 1116000000.0, 4424790000.0)
    assert comtrade.parse("not json", "US") == [] and comtrade.parse('{"data": null}', "US") == []


def test_fetch_exports_takes_the_newest_year_that_has_data():
    asked = []

    def get(url, params=None, **kw):
        asked.append(params["period"])
        return fixture("flows_comtrade_wheat_us.json") if params["period"] == "2024" else '{"data": []}'

    flows = comtrade.fetch_exports(842, "US", "1001", [2026, 2025, 2024, 2023], get=get, sleep=lambda s: None)
    assert asked == ["2026", "2025", "2024"] and len(flows) == 4


def _fake_get(url, params=None, **kw):
    if params["reporterCode"] == "643":
        return '{"data": []}'
    return fixture("flows_comtrade_wheat_us.json")


def test_refresh_keeps_the_strongest_partners_lists_missing_exporters_and_caches(monkeypatch):
    monkeypatch.setattr(refresh, "GRAIN", {"wheat": ("Wheat", "1001", ("US", "RU"))})
    monkeypatch.setattr(refresh, "MONEY_EXPORTERS", ("US",))
    now = datetime(2026, 10, 18, tzinfo=timezone.utc)
    doc = refresh.refresh(now, force=True, get=_fake_get, sleep=lambda s: None)
    wheat = doc["grain"]["wheat"]
    assert [f["to"] for f in wheat["flows"]] == ["MX", "PH", "JP", "TW"] or {f["to"] for f in wheat["flows"]} == {"MX", "PH", "JP", "TW"}
    assert wheat["missing"] == ["RU"] and all(f["t"] > 0 for f in wheat["flows"])
    assert refresh.load()["fetched_at"] == doc["fetched_at"]
    assert refresh.refresh(now, get=lambda *a, **k: pytest.fail("fresh cache must not fetch"), sleep=lambda s: None) == doc


def test_a_failed_exporter_keeps_its_previous_flows():
    old = {"grain": {"wheat": {"label": "Wheat", "flows": [{"from": "FR", "to": "MA", "usd": 5, "t": 5, "period": "2024"}], "missing": []}},
           "money": {"label": "m", "flows": [], "missing": []}}
    new = {"grain": {"wheat": {"label": "Wheat", "flows": [{"from": "US", "to": "MX", "usd": 9, "t": 9, "period": "2025"}], "missing": ["FR"]}},
           "money": {"label": "m", "flows": [], "missing": []}}
    out = refresh.merge(new, old)["grain"]["wheat"]
    assert {f["from"] for f in out["flows"]} == {"US", "FR"} and out["missing"] == []


# ── the document and its upload ───────────────────────────────────────────────────────────────
def _tracker_with_week():
    t = LaneTracker()
    for d in range(1, 10):
        base = T0 + (d - 1) * 86400
        for m in range(30 + d % 3):
            t.observe(m, *at("persian_gulf"), base + 100, lambda: "tanker")
            t.observe(m, *at("hormuz"), base + 100 + 14 * H, lambda: "tanker")
            t.observe(m, *at("persian_gulf"), base + 100 + 18 * H, lambda: "tanker")
            t.last.pop(m)
        t.days[day_of(base)]["secs"] = 86400.0
    return t


def test_the_document_carries_places_lanes_trade_and_the_honesty_fields(monkeypatch):
    monkeypatch.setattr(refresh, "GRAIN", {"wheat": ("Wheat", "1001", ("US",))})
    monkeypatch.setattr(refresh, "MONEY_EXPORTERS", ("US",))
    trade = refresh.refresh(datetime(2026, 10, 18, tzinfo=timezone.utc), force=True, get=_fake_get, sleep=lambda s: None)
    t = _tracker_with_week()
    now = T0 + 9 * 86400 + 6 * H
    doc = document.build(t.days, t.samples, trade, now)
    assert doc["v"] == 1 and [c["id"] for c in doc["classes"]][0] == "tanker"
    ais = doc["ais"]
    assert ais["days"] == 9 and ais["since"] == "2026-10-01" and "volunteer" in ais["note"] and ais["learning"] is False
    lane = next(x for x in ais["lanes"] if (x["a"], x["b"]) == ("persian_gulf", "hormuz"))
    assert lane["r7"] > 25 and set(lane["by"]) == {"tanker"} and lane["line"][0] == list(map(lambda v: round(v, 2), at("persian_gulf")))
    hormuz = next(p for p in ais["places"] if p["id"] == "hormuz")
    assert hormuz["kind"] == "chokepoint" and "z" in hormuz
    assert {p["id"] for p in ais["places"] if p["kind"] == "chokepoint"} >= {"hormuz", "suez", "panama"}     # chokepoints always listed
    assert doc["grain"]["commodities"]["wheat"]["flows"] and doc["money"]["flows"] and "annual" in doc["grain"]["note"].lower()
    assert {"US", "MX"} <= set(doc["places"]) and doc["places"]["MX"]["lat"]
    assert len(json.dumps(doc)) < 120_000


def test_publish_uploads_flows_json_and_stays_quiet_where_no_ships_are_held(monkeypatch):
    monkeypatch.setenv("SUPABASE_URL", "https://x.supabase.co")
    monkeypatch.setenv("SUPABASE_SERVICE_ROLE_KEY", "k")
    monkeypatch.setattr(refresh, "GRAIN", {"wheat": ("Wheat", "1001", ("US",))})
    monkeypatch.setattr(refresh, "MONEY_EXPORTERS", ("US",))
    sent = []
    http = lambda method, url, headers, body: sent.append((url, headers["Cache-Control"], body)) or 200   # noqa: E731
    now = T0 + 9 * 86400 + 6 * H
    out = publish.run(now=now, http=http, get=_fake_get)
    assert out["publish"] == {"skipped": "no lane aggregates on this machine (the stream service holds them)"} and not sent
    LaneTracker.write(_tracker_with_week().snapshot(now))
    out = publish.run(now=now, http=http, get=_fake_get)
    assert out["publish"]["assets"] == 1 and out["lanes"] >= 1 and out["grain_flows"] == 4
    url, cache, body = sent[0]
    assert url.endswith("/live/flows.json") and cache == "public, max-age=30"
    assert json.loads(body)["ais"]["days"] == 9
    assert store.read_json("flows_doc.json")["v"] == 1
