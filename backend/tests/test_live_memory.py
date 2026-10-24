"""Live memory: robust baseline math, learning state, anomaly scoring and persistence, coverage-gap suppression, rollup bounding,
daily series, the evidence block and the migration. Offline: synthetic hour files in a temp store, fake database connection."""

from __future__ import annotations

import gzip
import json
from datetime import datetime, timezone
from pathlib import Path

import pytest

from algent_backend.instruments import store as istore
from algent_backend.live import store as live_store
from algent_backend.live.memory import anomalies, areas, baseline, desk, flags, hours, robust, sampler, tick
from algent_backend.live.memory.baseline import Baseline

HORMUZ = "gate:hormuz"
MONDAY = int(datetime(2026, 9, 14, tzinfo=timezone.utc).timestamp() // 3600)       # a Monday 00:00 UTC


@pytest.fixture(autouse=True)
def _env(tmp_path, monkeypatch):
    monkeypatch.setenv("ALGENT_LIVE_STORE", str(tmp_path / "live"))
    monkeypatch.setenv("ALGENT_INSTRUMENTS_STORE", str(tmp_path / "istore"))
    monkeypatch.delenv("DATABASE_URL", raising=False)
    monkeypatch.setattr(tick, "rollup_day", lambda day: {"written": 0})        # file-heavy and tested on its own below


# ── robust statistics ───────────────────────────────────────────────────────────────────────────
def test_the_normal_ignores_an_outlier_week_and_never_has_less_than_poisson_spread():
    n = robust.normal_of([20, 21, 19, 20, 22, 90])               # one wild week moves neither median nor MAD much
    assert n is not None and n.median == 20.5 and n.sigma >= 1.4826
    assert robust.score(2, n) < -3.5 and abs(robust.score(21, n)) < 1
    quiet = robust.normal_of([16, 16, 16, 16, 16, 16])            # zero MAD: the damped counting floor (0.5 * sqrt 16 = 2) still applies
    assert quiet.sigma == 2.0 and robust.score(20, quiet) == 2.0 and robust.score(24, quiet) == 4.0
    empty = robust.zero_normal()
    assert empty.median == 0 and empty.sigma == 1.0 and robust.ratio(3, empty) is None


# ── baselines ───────────────────────────────────────────────────────────────────────────────────
def test_hour_of_week_slots_start_on_monday():
    assert baseline.slot_of("ship", MONDAY) == 0 and baseline.slot_of("ship", MONDAY + 25) == 25
    assert baseline.slot_of("ship", MONDAY + 168 * 3 + 5) == 5 and baseline.slot_of("fire", MONDAY + 77) == 0


def test_a_slot_is_learning_until_it_holds_enough_weeks_then_learned():
    bl = Baseline("ship")
    key = baseline.key_of("ship.tanker", HORMUZ)
    assert bl.estimate(key, 10) is None                           # unknown place in a young layer: not scored
    for _week in range(2):                                         # two weeks of days, same hours every day
        for day in range(7):
            for hod in range(24):
                bl.put(key, day * 24 + hod, 20.0, 0)
    est = bl.estimate(key, 10)                                    # slot 10 holds 2 weeks (< 3): trailing-days fallback, flagged learning
    assert est is not None and est.learning and est.median == 20.0
    bl.put(key, 10, 20.0, 0)
    est = bl.estimate(key, 10)
    assert est is not None and not est.learning                   # three weeks in that slot: learned


def test_too_little_history_gives_no_baseline_at_all():
    bl = Baseline("ship")
    key = baseline.key_of("ship.cargo", 123)
    for _ in range(2):
        bl.put(key, 5, 3.0, 0)
    assert bl.estimate(key, 5) is None                            # two values, not enough pooled to call anything normal


def test_a_mature_layer_knows_an_unseen_place_is_normally_empty():
    bl = Baseline("air")
    for _ in range(3 * 168):
        bl.note_hour(MONDAY)
    assert bl.mature()
    z = bl.estimate(baseline.key_of("air.military", 999), 7)
    assert z is not None and z.median == 0 and not z.learning
    bl.put(baseline.key_of("air.military", 999), 7, 0.0, 0)       # a place created after maturity starts from observed zeros
    assert bl.estimate(baseline.key_of("air.military", 999), 7).median == 0


def test_baseline_roundtrip_forgetting_and_a_fixed_size_ring(tmp_path):
    bl = Baseline("ship")
    k1, k2 = baseline.key_of("ship.tanker", 1), baseline.key_of("ship.tanker", 2)
    for i in range(20):                                           # far more than the ring depth: the ring stays bounded
        bl.put(k1, 3, float(i), 100)
    bl.put(k2, 3, 5.0, 10)
    assert len(bl.window(bl.index[k1], 3)) == flags.BASELINE_WEEKS
    assert bl.window(bl.index[k1], 3)[-1] == 19.0
    assert bl.forget(100 + flags.FORGET_DAYS + 1) == 2 and not bl.index
    bl.put(k1, 3, 2.5, 5)
    path = tmp_path / "b.bin.gz"
    bl.save(path)
    again = Baseline.load("ship", path)
    assert again.index == bl.index and again.window(0, 3) == bl.window(0, 3)
    path.write_bytes(b"not gzip")
    assert Baseline.load("ship", path).index == {}                # damaged file: start afresh, never crash
    fire = Baseline("fire")
    assert fire.geo.slots == 1 and fire.geo.depth == flags.FIRE_DEPTH


# ── hour files and sampling ─────────────────────────────────────────────────────────────────────
def test_hour_values_roundtrip_and_old_files_are_pruned():
    values = {"ship.tanker": {5: 3.25, 90: 1.0, HORMUZ: 12.5, "w": 200.0}, "ship.heard": {HORMUZ: 0.75}}
    hours.write_hour(MONDAY, "stream", 12, values)
    hours.write_hour(MONDAY, "firms", 1, {"fire.count": {7: 4.0}})
    h = hours.read_hour(MONDAY)
    assert h.samples == {"stream": 12, "firms": 1} and h.values["ship.tanker"] == values["ship.tanker"] and h.values["fire.count"] == {7: 4.0}
    assert hours.read_hour(MONDAY + 1).samples == {} and hours.stored_hours() == [MONDAY]
    old = (MONDAY + 1) * 3600 + flags.HOUR_KEEP_DAYS * 86400 + 7200
    assert hours.prune(old) == 2 and hours.stored_hours() == []


def test_one_hour_file_is_small_for_a_realistic_world():
    cells = {c: float(1 + c % 7) for c in range(10000, 10000 + 12000)}      # twelve thousand occupied cell-class entries
    hours.write_hour(MONDAY, "stream", 12, {"ship.cargo": cells})
    assert hours.disk_bytes() < 120_000


def _vessels(rows):
    return {"rows": rows}


def test_sampling_counts_classes_cells_areas_the_world_and_who_was_heard():
    now = 1_800_000_000.0
    rows = [[1, 56.4, 26.5, 0, 0, 0, int(now) - 30],              # tanker in the Hormuz gate, heard now
            [2, 56.5, 26.6, 0, 0, 1, int(now) - 30],              # cargo, same cell
            [3, 56.4, 26.5, 0, 0, 0, int(now) - 5000],            # tanker, stale (no recent message from it)
            [4, 10.5, 5.5, 0, 0, 3, int(now) - 5000]]            # fishing far away, not heard
    got = sampler.sample_ships(_vessels(rows), None, now)
    cell = areas.cell_of(26.5, 56.4)
    assert got["ship.tanker"][HORMUZ] == 2 and got["ship.tanker"][cell] == 2 and got["ship.tanker"]["w"] == 2
    assert got["ship.all"][HORMUZ] == 3 and got["ship.all"]["w"] == 4 and "ship.all" not in {k for k, v in got.items() if cell in v}
    assert got["ship.heard"][cell] == 1 and areas.cell_of(5.5, 10.5) not in got["ship.heard"]
    assert 0 < got["ship.heard"][HORMUZ] <= 1
    air = sampler.sample_air({"rows": [[9, 33.0, 44.0, 0, 0, 3, 0], [8, 34.0, 44.5, 0, 0, 0, 0], [7, 5.0, 5.0, 0, 0, 5, 0]]})
    assert air["air.military"]["region:black_sea"] == 1 and air["air.support"]["region:black_sea"] == 1       # surveillance is inside military
    assert air["air.military"]["w"] == 2 and air["air.all"]["region:black_sea"] == 2 and air["air.civil"]["w"] == 1


def test_the_sampler_writes_the_hour_mean_when_the_hour_turns_and_not_before():
    written = []
    sp = sampler.Sampler(writer=lambda *a: written.append(a))
    t0 = (MONDAY + 3) * 3600 + 10.0
    rows = lambda n: _vessels([[i, 56.4, 26.5, 0, 0, 1, int(t0)] for i in range(n)])      # noqa: E731
    assert sp.observe(rows(10), {"rows": []}, None, t0)
    assert not sp.observe(rows(99), {"rows": []}, None, t0 + 60)                         # not due yet
    assert sp.observe(rows(20), {"rows": []}, None, t0 + 600)
    assert written == []
    assert sp.observe(rows(5), {"rows": []}, None, t0 + 3600)                            # next hour: the previous one is flushed
    hour, source, n, values = written[0]
    assert (hour, source, n) == (MONDAY + 3, "stream", 2) and values["ship.cargo"][HORMUZ] == 15.0     # mean of 10 and 20


def test_fire_and_event_values_fold_into_cells_areas_and_the_world():
    doc = {"cells": [[37.0, 48.0, 12, 80], [37.1, 48.1, 3, 20], [100.0, -10.0, 2, 5]]}
    v = sampler.fire_values(doc)
    assert v["fire.count"]["fire:ukraine_front"] == 15 and v["fire.count"]["w"] == 17 and v["fire.frp"]["fire:ukraine_front"] == 100
    assert sampler.event_values("usgs", []) == {"quake.count": {}} and sampler.event_values("adsb", []) == {}
    assert sampler.record_fires(doc, MONDAY * 3600) and hours.read_hour(MONDAY).values["fire.count"]["w"] == 17


# ── detection, end to end through the tick ──────────────────────────────────────────────────────
def _hour(h, tanker=20.0, cargo=30.0, other=10.0, heard=1.0, world=1000.0, samples=12):
    v = {"ship.tanker": {HORMUZ: tanker}, "ship.cargo": {HORMUZ: cargo}, "ship.other": {HORMUZ: other},
         "ship.all": {HORMUZ: tanker + cargo + other, "w": world}, "ship.heard": {HORMUZ: heard}}
    hours.write_hour(h, "stream", samples, v)


def _run(first, last, **kw):
    for h in range(first, last):
        _hour(h, **kw)


def _settle(end_hour):
    """Process everything up to (not including) ``end_hour`` through the tick, as the timer would."""
    now = end_hour * 3600 + tick.SETTLE_SECONDS + 5
    out = {}
    for _ in range(10):
        out = tick.tick(now, publish=False)
        if not out.get("hours"):
            break
    return out


def _warmed(weeks=3):
    """Three weeks of a steady, mildly daily rhythm, learned."""
    _run(MONDAY, MONDAY + weeks * 168)
    _settle(MONDAY + weeks * 168)
    return MONDAY + weeks * 168


def test_a_steady_pattern_makes_no_anomaly_and_the_baseline_becomes_mature_and_learned():
    end = _warmed()
    st = tick.status()
    assert st["baselines"]["ship"]["mature"] and st["baselines"]["ship"]["places"] >= 4 and st["current"] == 0
    assert st["cursor"] == hours.iso_hour(end - 1)


def test_tankers_far_below_normal_over_several_hours_is_one_anomaly_with_a_plain_sentence():
    end = _warmed()
    _run(end, end + 2, tanker=7.0)
    _settle(end + 2)
    assert anomalies.read_current() == []                           # two hours is not persistence yet (PERSIST_HOURS = 3)
    _run(end + 2, end + 6, tanker=7.0)
    _settle(end + 6)
    (a,) = anomalies.read_current()
    assert (a.series, a.place_id, a.direction, a.provenance) == ("ship.tanker", HORMUZ, "below", "ohmega_derived")
    assert a.ends_at is None and a.hours >= 3 and a.normal == 20.0 and a.value == 7.0 and a.ratio == 0.35
    assert a.sentence.startswith("Strait of Hormuz: tankers 65% below normal for ") and "Iran" in a.countries
    assert 0 < a.confidence <= 1 and not a.learning
    log = [json.loads(line) for line in (hours.root() / "anomalies" / "log.jsonl").read_text().splitlines()]
    assert [e["event"] for e in log] == ["open"]
    _run(end + 6, end + 9)                                          # back to normal: the run closes, a close line is appended
    _settle(end + 9)
    (b,) = anomalies.read_current()
    assert b.id == a.id and b.ends_at is not None and not b.active
    assert [json.loads(line)["event"] for line in (hours.root() / "anomalies" / "log.jsonl").read_text().splitlines()] == ["open", "close"]


def test_a_single_odd_hour_is_noise():
    end = _warmed()
    _hour(end, tanker=2.0)
    _run(end + 1, end + 5)
    _settle(end + 5)
    assert anomalies.read_current() == []


def test_a_receiver_gap_where_the_rest_of_the_traffic_also_vanishes_is_not_ships_vanishing():
    end = _warmed()
    _run(end, end + 6, tanker=3.0, cargo=4.0, other=1.0)             # everything fell together: the place went quiet
    out = _settle(end + 6)
    assert anomalies.read_current() == []
    assert tick.load_state()["screened"].get("place_quiet", 0) > 0 or out["screened"].get("place_quiet", 0) > 0


def test_no_receiver_heard_in_the_place_suppresses_a_drop():
    end = _warmed()
    _run(end, end + 6, tanker=7.0, heard=0.1)
    _settle(end + 6)
    assert anomalies.read_current() == [] and tick.load_state()["screened"].get("no_receiver", 0) > 0


def test_a_world_wide_feed_dip_suppresses_every_drop_that_hour():
    end = _warmed()
    _run(end, end + 6, tanker=7.0, world=400.0)
    _settle(end + 6)
    assert anomalies.read_current() == [] and tick.load_state()["screened"].get("world_feed_low", 0) > 0


def test_a_missing_hour_is_unobserved_not_empty():
    end = _warmed()
    _run(end, end + 4, tanker=7.0)
    _run(end + 4, end + 8, samples=1)                                # service mostly down: too few samples, the hour is unobserved
    _settle(end + 8)
    (a,) = anomalies.read_current()
    assert a.active and a.hours <= 5                                 # the unobserved hours neither extend nor refute it
    assert Baseline.load("ship", hours.root() / "baseline_ship.bin.gz").window(0, 0)       # and the baseline was not taught zeros


def test_above_normal_in_a_normally_empty_place_is_flagged_and_a_lasting_change_becomes_normal():
    _run(MONDAY, MONDAY + 3 * 168)
    for h in range(MONDAY, MONDAY + 3 * 168):                        # military aircraft over the Black Sea: normally none
        hours.write_hour(h, "stream", 12, {**hours.read_hour(h).values, "air.military": {"region:black_sea": 0.0}})
    _settle(MONDAY + 3 * 168)
    end = MONDAY + 3 * 168
    for h in range(end, end + 5):
        hours.write_hour(h, "stream", 12, {**_values(h), "air.military": {"region:black_sea": 9.0}, "air.all": {"region:black_sea": 40.0, "w": 5000.0}})
    _settle(end + 5)
    got = [a for a in anomalies.read_current() if a.series == "air.military"]
    assert got and got[0].direction == "above" and got[0].normal == 0.0 and got[0].ratio is None
    assert "9 present, normally none" in got[0].sentence


def _values(h):
    return hours.read_hour(h).values if hours.read_hour(h).samples else {}


def test_a_young_baseline_is_marked_learning_and_needs_a_higher_score():
    _run(MONDAY, MONDAY + 4 * 24)                                    # four days only: no full weeks anywhere
    _settle(MONDAY + 4 * 24)
    end = MONDAY + 4 * 24
    _run(end, end + 5, tanker=14.0)                                  # -30%: well past 3.5 but under the learning bar of 6
    _settle(end + 5)
    assert anomalies.read_current() == []
    _run(end + 5, end + 12, tanker=2.0)
    _settle(end + 12)
    cur = anomalies.read_current()
    assert cur and cur[0].learning and cur[0].confidence <= 0.5


def test_an_incident_does_not_teach_the_baseline_that_it_is_normal():
    end = _warmed()
    key = baseline.key_of("ship.tanker", HORMUZ)
    before = Baseline.load("ship", hours.root() / "baseline_ship.bin.gz")
    _run(end, end + 12, tanker=5.0)
    _settle(end + 12)
    after = Baseline.load("ship", hours.root() / "baseline_ship.bin.gz")
    slot = baseline.slot_of("ship", end + 6)
    assert after.window(after.index[key], slot) == before.window(before.index[key], slot)      # frozen while the run is young


# ── anomalies: collapse, words, publishing ──────────────────────────────────────────────────────
def _anomaly(**kw):
    base = dict(id="x", series="ship.tanker", layer="ship", klass="tanker", place_kind="cell", place_id="c1", label="near 26°N 56°E",
                lat=26.5, lon=56.5, direction="below", starts_at="2026-10-01T00:00:00+00:00", hours=5, value=5, normal=20, ratio=0.25,
                score=5, confidence=0.6)
    return anomalies.Anomaly(**{**base, **kw})


def test_a_flagged_cell_inside_a_flagged_area_and_neighbours_merge_into_one_event():
    area = _anomaly(id="a", place_kind="gate", place_id=HORMUZ, label="Strait of Hormuz", lat=26.5, lon=56.4)
    inside = _anomaly(id="c-in", lat=26.5, lon=56.5)
    far = _anomaly(id="c-far", place_id="c2", lat=10.5, lon=50.5, confidence=0.7)
    near = _anomaly(id="c-near", place_id="c3", lat=11.5, lon=51.5, confidence=0.5)
    out = anomalies.collapse([inside, near, far, area])
    assert {a.id for a in out} == {"a", "c-far"}
    assert next(a for a in out if a.id == "c-far").n_cells == 2 and "(and 1 nearby cell)" in next(a for a in out if a.id == "c-far").sentence


def test_collapse_is_capped_and_puts_active_first():
    many = [_anomaly(id=f"c{i}", place_id=f"c{i}", lat=-60 + i * 3, lon=0, confidence=i / 100) for i in range(60)]
    many.append(_anomaly(id="done", place_id="cx", lat=70, lon=0, ends_at="2026-10-02T00:00:00+00:00", confidence=0.99))
    out = anomalies.collapse(many)
    assert len(out) == flags.MAX_PUBLISHED and out[0].active and "done" not in {a.id for a in out[:3]}


def test_words_for_magnitude_and_duration():
    assert anomalies.magnitude_text("below", 8, 20) == "60% below normal" and anomalies.magnitude_text("above", 50, 20) == "2.5x normal"
    assert anomalies.magnitude_text("above", 30, 20) == "50% above normal" and anomalies.duration_text(18) == "18 h"
    assert anomalies.duration_text(52) == "2 d 4 h" and anomalies.duration_text(24 * 9) == "9 d"


class _Cur:
    def __init__(self, log):
        self.log = log

    def execute(self, sql, params=None):
        self.log.append((sql, params))

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False


class _Conn(_Cur):
    def __init__(self):
        self.log = []

    def cursor(self):
        return _Cur(self.log)

    def commit(self):
        pass


def test_publish_upserts_current_retires_the_rest_and_prunes_old_rows():
    conn = _Conn()
    res = anomalies.publish([_anomaly(id="p1"), _anomaly(id="p2", ends_at="2026-10-02T00:00:00+00:00")], connect=lambda: conn)
    assert res == {"db": True, "anomalies": 2}
    sqls = [s for s, _p in conn.log]
    assert sum(s.strip().startswith("insert into live_anomalies") for s in sqls) == 2
    assert any("set active = false" in s for s in sqls) and any(s.startswith("delete from live_anomalies") for s in sqls)
    rows = [p for s, p in conn.log if s.strip().startswith("insert")]
    assert rows[0][0] == "p1" and rows[0][14] is True and rows[1][14] is False and rows[0][-1] == "ohmega_derived"
    assert anomalies.publish([_anomaly()])["db"] is False                    # no DATABASE_URL: a no-op


# ── daily rollups, the evidence block, catalog ──────────────────────────────────────────────────
def test_a_completed_day_becomes_a_series_and_a_thin_day_does_not():
    from algent_backend.instruments.catalog import get_series
    from algent_backend.live.memory.daily import rollup_day

    day = MONDAY // 24
    _run(MONDAY, MONDAY + 10)
    assert rollup_day(day) == {"observed_hours": 10, "written": 0}           # an outage is not a quiet strait
    _run(MONDAY + 10, MONDAY + 24)
    res = rollup_day(day)
    assert res["observed_hours"] == 24 and res["written"] >= 1
    sid = areas.daily_id(areas.BY_ID[HORMUZ], "tankers")
    obs = istore.history(sid)
    assert [(o.period, o.value) for o in obs] == [("2026-09-14", 20.0)] and get_series(sid).public_display
    assert rollup_day(day)["written"] == 0                                   # idempotent


def test_every_watched_area_has_its_daily_series_and_publishes_as_presence():
    from algent_backend.instruments.catalog import CATALOG
    from algent_backend.live.publish import _where

    ids = {s.id for s in CATALOG}
    wanted = [sid for sid, _a, _n in areas.daily_series()]
    assert wanted and all(w in ids for w in wanted) and len(wanted) == 6 * 3 + 6 * 4
    assert all(_where()[w][0] == "presence" for w in wanted)


def test_the_evidence_block_names_ohmega_cites_the_live_page_and_filters_by_country():
    end = _warmed()
    _run(end, end + 6, tanker=7.0)
    _settle(end + 6)
    text, urls, n = desk.block({"Iran"})
    assert n == 1 and text.startswith("OHMEGA LIVE ANOMALIES") and "tankers 65% below normal" in text and urls == {desk.LIVE_URL}
    assert desk.block({"Norway"}) == ("", set(), 0) and desk.block_all()[2] == 1
    roll = desk.theater_rollup({"Iran"}, "2026-10-05")
    assert roll["abnormal"][0]["series"] == "ship.tanker" and "Strait of Hormuz" not in roll["normal"] and roll["provenance"] == "ohmega_derived"
    desk.record_theater_day("t1", roll)
    line = json.loads((hours.root() / "anomalies" / "theater_days.jsonl").read_text().splitlines()[0])
    assert line["theater"] == "t1" and line["day"] == "2026-10-05"
    assert desk.theater_rollup({"Atlantis"}, "2026-10-05") == {}


def test_for_theater_uses_the_corroborated_countries():
    end = _warmed()
    _run(end, end + 6, tanker=7.0)
    _settle(end + 6)
    text, _urls, n, stood = desk.for_theater(lambda find: find("the Iran file"), lambda t, names: {x for x in names if x in t})
    assert n == 1 and stood == {"Iran"} and "Hormuz" in text


# ── the migration and the timer hook ────────────────────────────────────────────────────────────
def test_the_migration_makes_the_anomalies_public_read_only_and_the_publisher_writes_its_columns():
    from algent_backend.database import available

    sql = next(p for p in available() if p.stem == "011_live_anomalies").read_text(encoding="utf-8")
    assert "create table live_anomalies" in sql and "enable row level security" in sql and "for select to anon" in sql
    assert "revoke insert, update, delete, truncate on live_anomalies from anon, authenticated" in sql and "grant select on live_anomalies to anon" in sql
    for col in anomalies._COLUMNS:
        assert col in sql, col
    assert "ohmega_derived" in sql


def test_the_timer_runner_records_fires_and_settles_hours(monkeypatch):
    from algent_backend.live import runner
    from algent_backend.live.contracts import FeedResult

    class Fake:
        def __init__(self):
            pass

    monkeypatch.setattr(runner, "FEEDS", {"firms": type("F", (), {"fetch": staticmethod(lambda ctx: FeedResult(docs={"fires": {"as_of": "x", "detections": 1, "occupied": 1, "cells": [[37.0, 48.0, 12, 80]]}})),
                                                       "key_env": ""})()})
    monkeypatch.setattr(runner, "TIMER_FEEDS", ("firms",))
    now = datetime(2026, 10, 11, 10, 5, tzinfo=timezone.utc)
    out = runner.run(["firms"], get=lambda *a, **k: "", now=now, publish=False)
    assert "memory" not in out                                               # publish=False keeps the pass out
    assert hours.read_hour(hours.hour_of(now.timestamp())).values["fire.count"]["fire:ukraine_front"] == 12


def test_nothing_in_the_hour_store_survives_per_object():
    rows = [[123456789, 56.4, 26.5, 0, 0, 0, 0, "NAME", "DEST", "IR", 0]]
    sampler.Sampler(writer=lambda *a: hours.write_hour(*a)).observe(_vessels(rows), {"rows": []}, None, MONDAY * 3600 + 1)
    sp = sampler.Sampler()
    sp.observe(_vessels(rows), {"rows": []}, None, MONDAY * 3600 + 5)
    sp.flush()
    raw = b"".join(gzip.decompress(p.read_bytes()) for p in hours.hours_dir().glob("*.json.gz"))
    assert b"123456789" not in raw and b"NAME" not in raw and b"DEST" not in raw
    assert Path(hours.hours_dir()).is_dir() and live_store.root().exists()


def test_the_stream_cycle_feeds_the_sampler_from_the_built_snapshots():
    from algent_backend.live import stream
    from algent_backend.live.board import VesselBoard
    from algent_backend.live.sky import SkyBoard

    board, sky, now = VesselBoard(), SkyBoard(), (MONDAY + 2) * 3600 + 30.0
    board.report(1, 26.5, 56.4, now - 5, sog=0.0, ship_type=80)             # a tanker in the Hormuz gate
    taken = []
    sp = sampler.Sampler(writer=lambda *a: taken.append(a))
    docs = stream.build_docs(board, sky, now, sampler=sp)
    assert sp.n == 1 and "points" in docs
    sp.flush()
    assert taken[0][1] == "stream" and taken[0][3]["ship.tanker"][HORMUZ] == 1.0


def test_evidence_renders_the_anomaly_block_and_the_site_serves_the_endpoint_and_tool():
    from algent_backend.agent_system.agents.intel.sensing import Evidence

    assert "OHMEGA LIVE ANOMALIES" in Evidence(anomalies="OHMEGA LIVE ANOMALIES - x\n- y").render()
    site = Path(__file__).resolve().parents[2] / "sites" / "ohmega-monster" / "lib"
    assert 'path: "/anomalies"' in (site / "api" / "router.ts").read_text(encoding="utf-8")
    assert 'name: "get_live_anomalies"' in (site / "api" / "mcp-tools.ts").read_text(encoding="utf-8")
    assert 'live/anomalies.json' in (site / "live.ts").read_text(encoding="utf-8")
