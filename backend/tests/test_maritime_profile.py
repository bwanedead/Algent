"""Maritime behaviour memory: identity helpers, the profile book (sampling, change recording, bounds, persistence), the board hook.
Offline: synthetic reports into a temp store."""

from __future__ import annotations

import pytest

from algent_backend.live.board import VesselBoard
from algent_backend.maritime import flags, store
from algent_backend.maritime.profile import ProfileBook, clean_imo, fold_name, imo_valid, plausible_mmsi, same_name
from algent_backend.maritime.watch import Watch

T0 = 1_800_000_000.0           # an arbitrary instant (2027-01-15)
H = 3600.0


@pytest.fixture(autouse=True)
def _env(tmp_path, monkeypatch):
    monkeypatch.setenv("ALGENT_MARITIME_STORE", str(tmp_path / "maritime"))
    monkeypatch.setenv("ALGENT_LIVE_STORE", str(tmp_path / "live"))


def rows(*items):
    """(mmsi, lat, lon, sog, seen)"""
    return list(items)


# ── identity helpers ────────────────────────────────────────────────────────────────────────────
def test_imo_check_digit_and_cleaning():
    assert imo_valid("9074729") and not imo_valid("9074728") and not imo_valid("123")
    assert clean_imo("IMO 9074729") == "9074729" and clean_imo(0) == "" and clean_imo("12345") == "" and clean_imo(None) == ""


def test_names_compare_through_truncation_and_typos_but_not_renames():
    assert same_name("NORDIC STAR", "NORDIC STAR  ")                 # padding
    assert same_name("GRAND OCEAN TRADER XX", "GRAND OCEAN TRADER")   # truncated broadcast
    assert same_name("PACIFIC GLORY", "PACIFIC GL0RY")                # one wrong letter
    assert not same_name("PACIFIC GLORY", "SEA FALCON")
    assert same_name("AB", "ZZ")                                     # too short to compare: never a rename
    assert fold_name("Éole-7 !") == "EOLE 7"


def test_only_ship_stations_get_profiles():
    assert plausible_mmsi(636092000) and not plausible_mmsi(993001234) and not plausible_mmsi(111232511) and not plausible_mmsi(12345)
    book = ProfileBook()
    book.observe(rows((993001234, 1.0, 1.0, 5.0, T0), (636092000, 1.0, 1.0, 5.0, T0)), T0)
    assert list(book.profiles) == [636092000]


# ── identity memory ─────────────────────────────────────────────────────────────────────────────
def test_identity_records_renames_imo_changes_and_ignores_noise():
    book = ProfileBook()
    book.identity(636092000, "NORDIC STAR", "9074729", 81, T0)
    p = book.get(636092000)
    assert (p.name, p.imo, p.ship_type) == ("NORDIC STAR", "9074729", 81) and book.by_imo["9074729"] == {636092000}
    book.identity(636092000, "NORDIC STAR", 9074729, 81, T0 + 60)                 # same again: no change
    book.identity(636092000, "NORDIC STAR 2", None, 0, T0 + 120)                  # a fuller form of the same name
    book.identity(636092000, "", None, None, T0 + 130)                            # absent fields never erase
    assert p.changes == [] and p.name == "NORDIC STAR 2"
    book.identity(636092000, "SEA FALCON", "9321483", 81, T0 + H)
    kinds = [(c[1], c[2], c[3]) for c in p.changes]
    assert kinds == [("name", "NORDIC STAR 2", "SEA FALCON"), ("imo", "9074729", "9321483")]
    assert book.by_imo.get("9074729", set()) == set() and book.by_imo["9321483"] == {636092000}
    book.identity(636092000, None, None, 70, T0 + 2 * H)                          # tanker -> cargo family: recorded
    book.identity(636092000, None, None, 71, T0 + 2 * H)                          # within the cargo family: not a change
    assert [c[1] for c in p.changes][-1] == "type" and len(p.changes) == 3


def test_changes_are_bounded():
    book = ProfileBook()
    book.identity(636092000, "AAAA ONE", None, None, T0)
    words = ["ZEPHYR", "MARLIN", "OBSIDIAN", "KESTREL", "PINNACLE", "TUNDRA", "CORSAIR", "HALCYON", "VANGUARD", "LANTERN",
             "BRIGADE", "SAPPHIRE", "MONSOON", "TRIDENT", "WILLOW", "CITADEL", "NOMAD", "ORCHID", "FALCONER", "JUNIPER"]
    for i, w in enumerate(words):
        book.identity(636092000, w, None, None, T0 + i)
    assert len(book.get(636092000).changes) == flags.CHANGES_MAX


# ── positions ───────────────────────────────────────────────────────────────────────────────────
def test_samples_are_hourly_and_a_stationary_ship_keeps_one():
    book = ProfileBook()
    for i in range(0, 30 * 60, 60):                                               # 30 hours at one position, a report a minute
        book.observe(rows((636092000, 25.0, 55.0, 0.1, T0 + i * 60)), T0 + i * 60)
    p = book.get(636092000)
    assert len(p.points()) == 1 and p.last == T0 + 1740 * 60 and p.sog == pytest.approx(0.1)


def test_a_moving_ship_adds_a_sample_each_hour_capped_and_feeds_activity():
    book = ProfileBook()
    for h in range(flags.SAMPLES_MAX + 20):
        for k in range(3):                                                        # three reports inside the hour: one sample
            book.observe(rows((636092000, 25.0 + h * 0.01, 55.0, 12.0, T0 + h * H + k * 600)), T0 + h * H)
    p = book.get(636092000)
    assert len(p.points()) == flags.SAMPLES_MAX
    assert sum(book.activity.values()) == flags.SAMPLES_MAX + 20                  # one underway sample per hour per ship
    assert book.hourly_activity([c for c, _h in book.activity], int(T0 // H), int(T0 // H) + 2) > 0


def test_older_reports_never_rewind_a_profile():
    book = ProfileBook()
    book.observe(rows((636092000, 25.0, 55.0, 10.0, T0 + 100)), T0 + 100)
    assert book.observe(rows((636092000, 26.0, 56.0, 10.0, T0 + 50)), T0 + 100) == 0
    assert (book.get(636092000).lat, book.get(636092000).last) == (25.0, T0 + 100)


# ── bounds ──────────────────────────────────────────────────────────────────────────────────────
def test_stale_profiles_expire_and_the_cap_keeps_the_freshest(monkeypatch):
    book = ProfileBook()
    book.observe(rows((636092000, 25.0, 55.0, 10.0, T0)), T0)
    book.identity(636092001, "OLD ONE", "9074729", 80, T0)                        # identity but never a position: judged by first-heard
    for i in range(5):
        book.observe(rows((636093000 + i, 25.0, 55.0, 10.0, T0 + flags.PROFILE_KEEP_S - 100 + i)), T0 + flags.PROFILE_KEEP_S)
    assert book.prune(T0 + flags.PROFILE_KEEP_S + 100) == 2 and 636092000 not in book.profiles and "9074729" not in book.by_imo
    monkeypatch.setattr(flags, "PROFILE_MAX", 3)
    book.prune(T0 + flags.PROFILE_KEEP_S + 100)
    assert sorted(book.profiles) == [636093002, 636093003, 636093004]
    book.prune(T0 + flags.PROFILE_KEEP_S + flags.ACTIVITY_KEEP_H * H + 5 * H)
    assert book.activity == {}                                                    # old place activity is dropped too


# ── persistence ─────────────────────────────────────────────────────────────────────────────────
def test_the_book_survives_a_restart_with_activity_rebuilt():
    book = ProfileBook()
    book.identity(636092000, "NORDIC STAR", "9074729", 81, T0)
    book.identity(636092000, "SEA FALCON", None, None, T0 + 10 * H)
    for h in range(4):
        book.observe(rows((636092000, 25.0 + h * 0.2, 55.0, 12.0, T0 + h * H)), T0 + h * H)
    ProfileBook.write(store.profiles_path(), book.document())
    back = ProfileBook.load(store.profiles_path())
    a, b = book.get(636092000), back.get(636092000)
    assert (b.name, b.imo, b.ship_type, b.last) == (a.name, a.imo, a.ship_type, a.last) and b.changes == a.changes
    assert b.points() == pytest.approx(a.points()) and back.by_imo == {"9074729": {636092000}}
    assert back.activity == book.activity
    assert ProfileBook.load(store.root() / "missing.json.gz").profiles == {}       # a missing or torn file is an empty book


# ── the board hook and the watch ────────────────────────────────────────────────────────────────
def test_the_board_tells_the_watch_every_identity_and_the_watch_folds_the_board():
    board, watch = VesselBoard(), Watch()
    board.watch = watch
    board.message({"MetaData": {"MMSI": 636092000}, "Message": {"ShipStaticData": {"Name": "NORDIC STAR", "ImoNumber": 9074729, "Type": 81,
                                                                                    "Destination": "FUJAIRAH"}}}, T0)
    board.report(636092000, 25.0, 55.0, T0 + 60, sog=11.0, name="SEA FALCON")             # a name carried on a position report
    board.message({"MetaData": {"MMSI": 538001234}, "Message": {"StaticDataReport": {"ReportA": {"Name": "SMALL ONE"},
                                                                                       "ReportB": {"ShipType": 70}}}}, T0)
    p = watch.book.get(636092000)
    assert (p.imo, p.ship_type) == ("9074729", 81) and p.changes[0][1:] == ["name", "NORDIC STAR", "SEA FALCON"]
    assert watch.book.get(538001234).name == "SMALL ONE"
    out = watch.cycle(board, T0 + 120)
    assert out["updated"] == 1 and out["profiles"] == 2 and watch.book.get(636092000).lat == 25.0
    assert watch.persist_due(T0 + 120) and watch.document(T0 + 120)["v"] == 1 and not watch.persist_due(T0 + 130)
