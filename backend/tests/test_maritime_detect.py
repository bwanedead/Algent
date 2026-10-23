"""Maritime detectors on synthetic tracks, with their negative cases (left coverage, port, anchorage crowd, convoy, working craft), the
event store's bounds and the watch's pass. Offline."""

from __future__ import annotations

import pytest

from algent_backend.maritime import flags, store
from algent_backend.maritime.contracts import BehaviourEvent
from algent_backend.maritime.detect import gap, identity, loiter, sanctioned, sts
from algent_backend.maritime.detect.common import Context, Fresh
from algent_backend.maritime.profile import ProfileBook
from algent_backend.maritime.sites import Exclusion
from algent_backend.maritime.watch import Watch, link_related
from algent_backend.sanctions.contracts import Entry

T0 = 1_800_000_000.0
H = 3600.0
LAT, LON = 20.0, 60.0                      # open ocean, outside every named area
VICTIM, LIBERIA, RUSSIA = 636092000, 636092111, 273100200


@pytest.fixture(autouse=True)
def _env(tmp_path, monkeypatch):
    monkeypatch.setenv("ALGENT_MARITIME_STORE", str(tmp_path / "maritime"))
    monkeypatch.setenv("ALGENT_LIVE_STORE", str(tmp_path / "live"))


def heard_all(now: float, lat: float = LAT, lon: float = LON) -> dict[int, float]:
    from algent_backend.maritime.geomath import block

    return {c: now - 60 for c in block(lat, lon)}


def ctx(book, now, *, fresh=(), excl=None, heard=None, blind=0.0, idx=None) -> Context:
    return Context(now, book, heard if heard is not None else heard_all(now), list(fresh), excl or Exclusion(), blind, idx)


def lane(book: ProfileBook, hours: range, *, n: int = 6) -> None:
    """n other ships steaming through the block, one report an hour each."""
    for h in hours:
        for i in range(n):
            book.observe([(636200000 + i, LAT + 0.1 * i, LON + 0.05 * h, 13.0, T0 + h * H)], T0 + h * H)


def victim_goes_quiet(book: ProfileBook, last_hour: int = 6, sog: float = 12.0) -> None:
    for h in range(last_hour + 1):
        book.observe([(VICTIM, LAT + 0.02 * h, LON + 0.1 * h, sog, T0 + h * H)], T0 + h * H)
    book.identity(VICTIM, "NORDIC STAR", "9074729", 81, T0)


# ── 1. AIS gap ──────────────────────────────────────────────────────────────────────────────────
def test_a_vessel_that_goes_quiet_in_heard_water_is_a_gap():
    book = ProfileBook()
    lane(book, range(0, 15))
    victim_goes_quiet(book)
    now = T0 + 14 * H
    out = gap.detect(ctx(book, now), {})
    assert len(out) == 1
    e = out[0]
    assert e.kind == "ais_gap" and e.mmsi == VICTIM and e.state == "ongoing" and e.ended_at is None and e.flag == "LR"
    assert e.detail["silence_h"] == 8.0 and e.detail["before_per_h"] >= flags.GAP_MIN_BEFORE and e.confidence > 0.5
    assert "receivers were alive" in e.rationale and e.evidence[-1][4] == "last heard"


def test_a_ship_that_left_receiver_coverage_is_not_going_dark():
    book = ProfileBook()
    lane(book, range(0, 7))                      # the neighbours go quiet at the same moment: the receivers were lost
    victim_goes_quiet(book)
    c = ctx(book, T0 + 14 * H)
    assert gap.detect(c, {}) == [] and "gap:receiver_gap" in c.notes


def test_receivers_must_be_alive_now_too():
    book = ProfileBook()
    lane(book, range(0, 15))
    victim_goes_quiet(book)
    c = ctx(book, T0 + 14 * H, heard={})
    assert gap.detect(c, {}) == [] and "gap:receiver_gap" in c.notes


@pytest.mark.parametrize("why,kw,setup", [
    ("thin water", {}, "empty"),
    ("stopped at last report", {}, "stopped"),
    ("port area", {"excl": Exclusion(is_land=lambda la, lo: True)}, "lane"),
    ("stream was down", {"blind": T0 + 8 * H}, "lane"),
    ("too short", {"now": T0 + 10 * H}, "lane"),
])
def test_gap_negative_cases(why, kw, setup):
    book = ProfileBook()
    if setup != "empty":
        lane(book, range(0, 15))
    victim_goes_quiet(book, sog=0.3 if setup == "stopped" else 12.0)
    now = kw.pop("now", T0 + 14 * H)
    assert gap.detect(ctx(book, now, **kw), {}) == [], why


def test_a_gap_closes_when_the_vessel_is_heard_again_and_says_how_far():
    book = ProfileBook()
    lane(book, range(0, 15))
    victim_goes_quiet(book)
    first = gap.detect(ctx(book, T0 + 14 * H), {})[0]
    book.observe([(VICTIM, LAT + 4.0, LON + 5.0, 11.0, T0 + 15 * H)], T0 + 15 * H)
    back = gap.detect(ctx(book, T0 + 15 * H + 60), {first.id: first})
    assert len(back) == 1 and back[0].state == "ended" and back[0].ended_at is not None
    assert back[0].detail["reappeared"]["moved_while_dark"] and back[0].detail["reappeared"]["km"] > 400
    assert back[0].confidence > first.confidence and "reappeared" in back[0].summary
    quiet_again = gap.detect(ctx(book, T0 + 15 * H + 120), {back[0].id: back[0]})
    assert quiet_again == []                       # a closed gap is not re-opened


def test_a_gap_never_resolved_is_closed_unresolved():
    book = ProfileBook()
    lane(book, range(0, 15))
    victim_goes_quiet(book)
    first = gap.detect(ctx(book, T0 + 14 * H), {})[0]
    out = gap.detect(ctx(book, T0 + 6 * H + flags.GAP_UNRESOLVED_S + 10), {first.id: first})
    assert out[0].state == "unresolved" and out[0].ended_at


# ── 2. STS ──────────────────────────────────────────────────────────────────────────────────────
def fresh(mmsi, lat, lon, sog, now, typ=81):
    return Fresh(mmsi, lat, lon, sog, now, typ, "")


def run_encounter(pair, *, hours=2.5, others=(), excl=None, state=None):
    book, state = ProfileBook(), state if state is not None else {}
    out: list[BehaviourEvent] = []
    t = T0
    while t <= T0 + hours * H:
        fr = [*(fresh(m, la, lo, sg, t, ty) for m, la, lo, sg, ty in pair), *(fresh(*o, t, 70) if False else Fresh(o[0], o[1], o[2], o[3], t, 70, "") for o in others)]
        out = sts.detect(ctx(book, t, fresh=fr, excl=excl), state)
        t += flags.DETECT_SECONDS
    return out, state


SIDE = [(636000001, 20.0, 60.0, 0.3, 81), (636000002, 20.0, 60.0 + 0.002, 0.2, 70)]       # ~210 m apart, a tanker and a cargo ship


def test_two_ships_alongside_for_hours_in_open_water_is_an_sts_candidate():
    out, state = run_encounter(SIDE)
    assert len(out) == 1
    e = out[0]
    assert e.kind == "sts" and {e.mmsi, e.mmsi2} == {636000001, 636000002} and e.state == "ongoing"
    assert 150 <= e.detail["median_m"] <= 260 and e.detail["duration_h"] >= 2.0 and e.confidence > 0.4
    assert "possible ship-to-ship transfer" in e.summary and len(e.evidence) >= 20


def test_an_encounter_shorter_than_the_minimum_is_not_reported():
    out, _ = run_encounter(SIDE, hours=1.5)
    assert out == []


def test_the_encounter_closes_when_the_pair_parts():
    _, state = run_encounter(SIDE)
    book = ProfileBook()
    later = T0 + 2.5 * H + flags.STS_LOST_S + 600
    out = sts.detect(ctx(book, later, fresh=[fresh(636000001, 20.0, 60.0, 9.0, later), fresh(636000002, 20.5, 60.5, 9.0, later, 70)]), state)
    assert len(out) == 1 and out[0].state == "ended" and out[0].ended_at and state["enc"] == {}


@pytest.mark.parametrize("why,pair,kw", [
    ("port", SIDE, {"excl": Exclusion(is_land=lambda la, lo: True)}),
    ("two cargo ships, no tanker", [(1, 20.0, 60.0, 0.3, 71), (2, 20.0, 60.002, 0.3, 70)], {}),
    ("too far apart", [(1, 20.0, 60.0, 0.3, 81), (2, 20.0, 60.008, 0.3, 70)], {}),
    ("a tug alongside", [(1, 20.0, 60.0, 0.3, 81), (2, 20.0, 60.002, 0.3, 52)], {}),
    ("a normal convoy underway", [(1, 20.0, 60.0, 12.0, 81), (2, 20.0, 60.002, 12.0, 81)], {}),
    ("an anchorage crowd", SIDE, {"others": [(10 + i, 20.0 + 0.004 * i, 60.01, 0.2) for i in range(7)]}),
])
def test_sts_negative_cases(why, pair, kw):
    out, state = run_encounter(pair, **kw)
    assert out == [] and state.get("enc", {}) == {}, why


def test_a_pair_together_for_days_is_marked_down_as_a_layup():
    long, _ = run_encounter(SIDE, hours=flags.STS_LAYUP_H + 2)
    short, _ = run_encounter(SIDE, hours=4)
    assert long[0].confidence < short[0].confidence


# ── 3. identity ─────────────────────────────────────────────────────────────────────────────────
def test_renames_alternation_imo_changes_invalid_imo_and_flag_hopping():
    book = ProfileBook()
    book.observe([(VICTIM, LAT, LON, 10.0, T0)], T0)
    book.identity(VICTIM, "NORDIC STAR", "9074729", 81, T0)
    book.identity(VICTIM, "SEA FALCON", None, None, T0 + H)                    # rename
    book.identity(VICTIM, "NORDIC STAR", None, None, T0 + 2 * H)               # back to an earlier name: alternating
    book.identity(VICTIM, None, "9321483", None, T0 + 3 * H)                   # IMO changed on one MMSI
    book.identity(LIBERIA, "BAD NUMBER", "1234568", 81, T0)                    # fails the check digit
    book.observe([(LIBERIA, LAT, LON, 10.0, T0)], T0)
    book.identity(RUSSIA, "SAME HULL", "9321483", 81, T0)                      # the IMO now also under a Russian MMSI
    book.observe([(RUSSIA, LAT, LON, 10.0, T0 + 60)], T0 + 60)
    out = identity.detect(ctx(book, T0 + 4 * H), {})
    subs = sorted(e.detail["change"] for e in out)
    assert subs == ["alternating", "flag_hop", "imo_change", "imo_invalid", "rename"]
    flag_hop = next(e for e in out if e.detail["change"] == "flag_hop")
    assert set(flag_hop.detail["flags"]) == {"LR", "RU"} and flag_hop.mmsi2 in (VICTIM, RUSSIA)
    assert all(0 < e.confidence <= 1 and e.state == "ended" and e.rationale for e in out)
    again = identity.detect(ctx(book, T0 + 5 * H), {})
    assert sorted(e.id for e in again) == sorted(e.id for e in out)           # deterministic ids: the same finding is one event


def test_ordinary_name_noise_is_not_an_identity_event():
    book = ProfileBook()
    book.identity(VICTIM, "NORDIC STAR", "9074729", 81, T0)
    book.identity(VICTIM, "NORDIC STAR  ", None, None, T0 + 60)
    book.identity(VICTIM, "NORDIC STAR XX", None, None, T0 + 120)             # a longer broadcast of the same name
    book.identity(VICTIM, "NORDIC STAK", None, None, T0 + 180)                # a mistyped letter
    assert identity.detect(ctx(book, T0 + H), {}) == []


# ── 4. sanctioned ───────────────────────────────────────────────────────────────────────────────
def listing():
    ofac = {"1": Entry(ref="1", name="NORDIC STAR", type="vessel", imo="9074729", flag="LR", programmes=["IRAN"], owner="X Shipping"),
            "2": Entry(ref="2", name="PACIFIC GLORY", type="vessel", flag="PA", programmes=["RUSSIA-EO14024"]),
            "3": Entry(ref="3", name="SOME PERSON", type="person")}
    return sanctioned.SanctionIndex.build({"ofac": ofac}, T0)


def test_a_listed_vessel_is_matched_by_imo_or_by_name_and_flag_never_by_name_alone():
    book = ProfileBook()
    book.identity(VICTIM, "RENAMED SHIP", "9074729", 81, T0)                   # IMO match despite another name
    book.observe([(VICTIM, LAT, LON, 10.0, T0)], T0)
    book.identity(636000333, "PACIFIC GLORY", None, 81, T0)                    # Liberian name twin of a PANAMA-flag listing
    book.identity(353000444, "PACIFIC GLORY", None, 81, T0)                    # MID 353 = Panama: name + flag
    book.observe([(636000333, LAT, LON, 8.0, T0), (353000444, LAT + 1, LON, 8.0, T0)], T0)
    out = sanctioned.detect(ctx(book, T0 + 600, idx=listing()), {})
    by = {e.mmsi: e for e in out}
    assert set(by) == {VICTIM, 353000444}
    assert by[VICTIM].detail["basis"] == "imo" and by[VICTIM].confidence == flags.SANCTION_CONF["imo"] and by[VICTIM].detail["list"]
    assert by[353000444].detail["basis"] == "name_flag" and by[353000444].confidence == flags.SANCTION_CONF["name_flag"]
    assert by[VICTIM].detail["asset_id"] == "og-xx-vessel-imo9074729" and by[VICTIM].state == "ongoing"
    assert sanctioned.detect(ctx(book, T0 + 3 * H, idx=listing()), {})[0].state == "ended"      # not heard for hours: a sighting that ended
    assert sanctioned.detect(ctx(book, T0 + 600, idx=None), {}) == []


def test_a_former_name_matches_and_started_at_is_kept_across_passes():
    book = ProfileBook()
    book.identity(353000444, "PACIFIC GLORY", None, 81, T0)
    book.identity(353000444, "SEA FALCON", None, None, T0 + 10)                # renamed after being listed under its old name
    book.observe([(353000444, LAT, LON, 8.0, T0 + 20)], T0 + 20)
    first = sanctioned.detect(ctx(book, T0 + 600, idx=listing()), {})
    assert len(first) == 1
    book.observe([(353000444, LAT + 0.5, LON, 8.0, T0 + 1200)], T0 + 1200)
    again = sanctioned.detect(ctx(book, T0 + 1300, idx=listing()), {first[0].id: first[0]})
    assert again[0].id == first[0].id and again[0].started_at == first[0].started_at and again[0].lat != first[0].lat


# ── 5. loitering ────────────────────────────────────────────────────────────────────────────────
HORMUZ = (26.3, 56.4)


def dwell(typ=81, hours=5.0, others=0, excl=None, at=HORMUZ, sog=1.0):
    state: dict = {}
    out: list[BehaviourEvent] = []
    t = T0
    while t <= T0 + hours * H:
        fr = [Fresh(636000009, at[0], at[1], sog, t, typ, ""), *(Fresh(900 + i, at[0] + 0.003 * i, at[1], 0.4, t, 70, "") for i in range(others))]
        out = loiter.detect(ctx(ProfileBook(), t, fresh=fr, excl=excl), state)
        t += flags.DETECT_SECONDS
    return out, state


def test_a_long_slow_dwell_in_a_sensitive_zone_is_reported_with_its_reason():
    out, _ = dwell()
    assert len(out) == 1 and out[0].kind == "loiter" and out[0].detail["zone"] == "hormuz" and out[0].detail["duration_h"] >= 4
    assert out[0].area == "Strait of Hormuz" and "Iran" in out[0].countries and "longer than" in out[0].rationale
    cable, _ = dwell(at=(59.7, 24.5))
    assert cable[0].detail["zone"] == "gulf_of_finland_cables" and cable[0].detail["proxy"] is True


@pytest.mark.parametrize("why,kw", [
    ("too short", {"hours": 3.0}),
    ("fishing vessel", {"typ": 30}),
    ("a tug", {"typ": 52}),
    ("moving through", {"sog": 9.0}),
    ("anchorage crowd", {"others": 8}),
    ("port area", {"excl": Exclusion(is_land=lambda la, lo: True)}),
    ("outside any zone", {"at": (10.0, -30.0)}),
])
def test_loiter_negative_cases(why, kw):
    out, state = dwell(**kw)
    assert out == [], why


def test_a_dwell_closes_after_the_vessel_leaves():
    _, state = dwell()
    later = T0 + 5 * H + flags.LOITER_LOST_S + 600
    out = loiter.detect(ctx(ProfileBook(), later), state)
    assert len(out) == 1 and out[0].state == "ended" and state["dwell"] == {}


# ── related flags, the store and the watch ──────────────────────────────────────────────────────
def mk(kind="ais_gap", mmsi=VICTIM, conf=0.5, **kw):
    base = dict(id=f"mb-{kind}-{mmsi}", kind=kind, mmsi=mmsi, started_at="2027-01-15T00:00:00+00:00", last_seen="2027-01-15T00:00:00+00:00")
    return BehaviourEvent(**{**base, "confidence": conf, **kw})


def test_a_vessel_with_a_second_kind_of_flag_is_raised_without_ratcheting():
    gap_e, sanc = mk(), mk("sanctioned", conf=0.95)
    out = link_related([gap_e], {sanc.id: sanc}, T0)
    assert out[0].confidence == 0.7 and out[0].detail["related"] == ["sanctioned"]
    again = link_related(out, {sanc.id: sanc}, T0)                              # re-linking an already linked event does not climb
    assert again[0].confidence == 0.7
    assert link_related([mk(mmsi=1)], {sanc.id: sanc}, T0)[0].confidence == 0.5


def test_the_store_upserts_logs_state_changes_and_stays_bounded(monkeypatch):
    now = T0 + 40 * 86400
    a = mk(conf=0.5)
    assert store.upsert([a], now) == {"new": 1, "changed": 0, "kept": 1}
    assert store.upsert([a], now + 60)["new"] == 0                              # identical: nothing written
    closed_ev = a.model_copy(update={"state": "ended", "ended_at": "2027-02-20T00:00:00+00:00"})
    assert store.upsert([closed_ev], now + 120) == {"new": 0, "changed": 1, "kept": 1}
    log = (store.root() / "log.jsonl").read_text(encoding="utf-8").splitlines()
    assert [__import__("json").loads(x)["state"] for x in log] == ["open", "ended"]
    old = mk(mmsi=7, ended_at="2026-01-01T00:00:00+00:00", state="ended")
    store.upsert([old], now)
    assert old.id not in store.read_current()                                   # ended long ago: expired from the picture
    monkeypatch.setattr(flags, "EVENTS_MAX", 3)
    store.upsert([mk(mmsi=100 + i, last_seen=f"2027-02-{10 + i:02d}T00:00:00+00:00", ended_at=None) for i in range(6)], now)
    cur = store.read_current()
    assert len(cur) == 3 and all(e.mmsi >= 103 for e in cur.values())            # the newest kept


def _lines():
    return [__import__("json").loads(x) for x in (store.root() / "log.jsonl").read_text(encoding="utf-8").splitlines()]


def test_the_log_writes_transitions_only_and_never_ongoing_or_a_repeat(monkeypatch):
    now = T0 + 40 * 86400
    sanc = mk("sanctioned", conf=0.95, started_at="2027-02-09T00:00:00+00:00", last_seen="2027-02-09T00:00:00+00:00")
    store.upsert([sanc], now)
    stale = sanc.model_copy(update={"state": "ended", "ended_at": "2027-02-09T01:00:00+00:00"})
    store.upsert([stale], now + 300)                                              # went quiet
    store.upsert([sanc.model_copy(update={"last_seen": "2027-02-09T02:00:00+00:00"})], now + 600)       # seen again: back to ongoing, not a transition
    store.upsert([stale.model_copy(update={"last_seen": "2027-02-09T03:00:00+00:00"})], now + 900)      # flapped to ended again
    rows = _lines()
    assert [(r["id"], r["state"]) for r in rows] == [(sanc.id, "open"), (sanc.id, "ended")]
    assert set(rows[0]) == {"id", "kind", "state", "mmsi", "imo", "name", "ship_class", "at", "lat", "lon", "area", "confidence"}
    assert len((store.root() / "log.jsonl").read_text(encoding="utf-8")) < 600     # compact, not the 1.9 KB object


def test_an_event_the_picture_let_go_of_is_not_logged_again_when_a_detector_finds_it(monkeypatch):
    now = T0 + 40 * 86400
    monkeypatch.setattr(flags, "EVENTS_MAX", 2)
    done = [mk("identity", mmsi=500 + i, state="ended", started_at=f"2027-02-0{i + 1}T00:00:00+00:00", ended_at=f"2027-02-0{i + 1}T00:00:00+00:00",
               last_seen=f"2027-02-0{i + 1}T00:00:00+00:00") for i in range(4)]
    store.upsert(done, now)
    assert len(store.read_current()) == 2                                          # the cap cut the two oldest
    for _ in range(3):                                                             # every later pass re-derives all four
        assert store.upsert(done, now + 300)["new"] == 0
    assert [r["state"] for r in _lines()] == ["open"] * 4                          # one open each, never again


def test_cooldown_is_per_vessel_and_kind_and_derived_from_the_detector_minimum():
    now = T0 + 40 * 86400
    a = mk(mmsi=900, id="mb-g1")
    b = mk(mmsi=900, id="mb-g2", started_at="2027-02-09T00:30:00+00:00")           # same vessel, same kind, half an hour on: the same gap
    c = mk("sts", mmsi=900, id="mb-s1")                                           # same vessel, other kind
    store.upsert([a], now)
    store.upsert([b, c], now + 1800)
    assert [(r["id"], r["state"]) for r in _lines()] == [("mb-g1", "open"), ("mb-s1", "open")]
    assert "mb-g2" in store.read_current()                                         # still in the picture, only the log skips it
    d = mk(mmsi=900, id="mb-g3")
    store.upsert([d], now + flags.LOG_COOLDOWN_S["ais_gap"] + 60)
    assert _lines()[-1]["id"] == "mb-g3"


class FakeBoard:
    def __init__(self):
        from algent_backend.live.ais_memory import Coverage, StaticMemory

        self.v, self.name, self.static, self.coverage = {}, {}, StaticMemory(), Coverage()


def test_the_watch_runs_a_pass_persists_state_and_marks_a_restart_blind(monkeypatch):
    board, w = FakeBoard(), Watch(excl=Exclusion())
    w.sanctions = listing()
    for h in range(0, 15):
        for i in range(6):
            board.v[636200000 + i] = [LAT + 0.1 * i, LON + 0.05 * h, 0, 13.0, T0 + h * H]
            board.coverage.hear(LAT + 0.1 * i, LON + 0.05 * h, T0 + h * H)
        if h <= 6:
            board.v[VICTIM] = [LAT, LON + 0.1 * h, 0, 12.0, T0 + h * H]
        w.last_detect = 0 if h == 14 else T0 + h * H                           # one detector pass, at the end
        w.state["last_cycle"] = T0 + h * H - 60                                # the test's cycles are an hour apart: not a stream outage
        w.cycle(board, T0 + h * H)
    assert w.last_account["new"] >= 1 and "errors" not in w.last_account, w.last_account
    cur = store.read_current()
    assert any(e.kind == "ais_gap" and e.mmsi == VICTIM for e in cur.values())
    assert store.read_state()["last_cycle"] == T0 + 14 * H
    reborn = Watch.load()
    reborn.cycle(board, T0 + 14 * H + 3 * H)                                   # three hours later: the stream was down
    assert reborn.state["blind_until"] == T0 + 17 * H


def test_a_broken_detector_does_not_silence_the_rest(monkeypatch):
    board, w = FakeBoard(), Watch(excl=Exclusion())
    monkeypatch.setattr(gap, "detect", lambda *_a, **_k: (_ for _ in ()).throw(RuntimeError("boom")))
    out = w.detect(board, T0)
    assert out["errors"]["gap"].startswith("RuntimeError") and out["found"] == 0
