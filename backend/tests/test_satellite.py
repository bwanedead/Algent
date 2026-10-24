"""Satellite watch: PNG decode, the change score and its honesty rules (cloud is inconclusive, little history is learning), the data-driven watch
list and its rotation, a whole pass against a fake imagery source, and the publish shape with provenance. No network."""

from __future__ import annotations

import struct
import zlib
from datetime import datetime, timedelta, timezone

import pytest

from algent_backend.geoledger.contracts import Asset, StatusEvent, event_id
from algent_backend.geoledger.store import Ledger
from algent_backend.satellite import change, document, flags, png, run, store, watchlist
from algent_backend.satellite.sources import Scene

W = 32
NOW = datetime(2026, 10, 18, 6, 0, tzinfo=timezone.utc)


@pytest.fixture(autouse=True)
def _store(tmp_path, monkeypatch):
    monkeypatch.setenv("ALGENT_LIVE_STORE", str(tmp_path / "live"))


# ── helpers ──────────────────────────────────────────────────────────────────────────────────
def rgb_chip(fn=lambda x, y: (100, 120, 90), w: int = W) -> bytes:
    px = bytearray()
    for y in range(w):
        for x in range(w):
            px += bytes(fn(x, y))
    return png.encode(w, w, 3, bytes(px))


def scl_chip(fn=lambda x, y: 4, w: int = W) -> bytes:
    """A scene-classification chip as the service renders it: class * 255 / 11 as grey."""
    return png.encode(w, w, 1, bytes(round(fn(x, y) * 255 / 11) for y in range(w) for x in range(w)))


def classes(fn=lambda x, y: 4, w: int = W) -> list[int]:
    return change.scl_classes(png.decode(scl_chip(fn, w)))


def pair(a_fn, b_fn, a_scl=lambda x, y: 4, b_scl=lambda x, y: 4):
    return change.compare(png.decode(rgb_chip(a_fn)), classes(a_scl), png.decode(rgb_chip(b_fn)), classes(b_scl))


def _filtered_png(w: int, h: int, pixels: bytes, ft: int, bpp: int = 3) -> bytes:
    """A PNG whose every row uses filter type ``ft`` (1 sub, 2 up, 3 average, 4 paeth): the inverse of the decoder's unfilter."""
    stride = w * bpp
    rows, prev = [], bytes(stride)
    for y in range(h):
        row = pixels[y * stride:(y + 1) * stride]
        out = bytearray()
        for i in range(stride):
            a = row[i - bpp] if i >= bpp else 0
            b = prev[i]
            c = prev[i - bpp] if i >= bpp else 0
            pred = {1: a, 2: b, 3: (a + b) >> 1, 4: png._paeth(a, b, c)}[ft]
            out.append((row[i] - pred) & 255)
        rows.append(bytes([ft]) + bytes(out))
        prev = row

    def chunk(k: bytes, body: bytes) -> bytes:
        return struct.pack(">I", len(body)) + k + body + struct.pack(">I", zlib.crc32(k + body) & 0xFFFFFFFF)

    return b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", struct.pack(">IIBBBBB", w, h, 8, 2, 0, 0, 0)) + chunk(b"IDAT", zlib.compress(b"".join(rows))) + chunk(b"IEND", b"")


# ── PNG decode ───────────────────────────────────────────────────────────────────────────────
@pytest.mark.parametrize("ft", [0, 1, 2, 3, 4])
def test_every_png_filter_decodes_back_to_the_pixels(ft):
    px = bytes((x * 7 + y * 13 + c * 29) & 255 for y in range(9) for x in range(11) for c in range(3))
    data = png.encode(11, 9, 3, px) if ft == 0 else _filtered_png(11, 9, px, ft)
    img = png.decode(data)
    assert (img.width, img.height, img.channels) == (11, 9, 3) and img.pixels == px


def test_rgba_exposes_alpha_and_a_non_png_is_refused():
    img = png.decode(png.encode(2, 2, 4, bytes([1, 2, 3, 0, 4, 5, 6, 255] * 2)))
    assert img.alpha == bytes([0, 255, 0, 255]) and img.band(0) == bytes([1, 4, 1, 4])
    with pytest.raises(ValueError):
        png.decode(b"<html>429 too many requests</html>")


# ── change score ─────────────────────────────────────────────────────────────────────────────
def textured(x: int, y: int) -> tuple[int, int, int]:
    v = 80 + (x * 5 + y * 3) % 60
    return (v, v + 10, v - 10)


def test_identical_chips_score_zero():
    r = pair(textured, textured)
    assert r["score"] == 0 and r["changed_frac"] == 0 and r["valid_share"] == 1


def test_a_global_brightness_shift_is_normalised_away():
    r = pair(textured, lambda x, y: tuple(c + 25 for c in textured(x, y)))
    assert r["score"] < 0.002 and r["changed_frac"] == 0


def test_a_local_change_scores_and_marks_its_share_of_pixels():
    r = pair(textured, lambda x, y: (250, 40, 40) if x < 8 and y < 8 else textured(x, y))        # 64 of 1024 pixels
    assert r["score"] > 0.02
    assert 0.05 < r["changed_frac"] < 0.07


def test_cloudy_pixels_are_left_out_and_a_cloudy_pair_has_no_verdict():
    cloud = lambda x, y: 9 if x < 22 else 4                                                       # ~69% cloud in the second chip
    r = pair(textured, lambda x, y: (255, 255, 255) if x < 22 else textured(x, y), b_scl=cloud)
    assert r["valid_share"] < flags.MIN_VALID_SHARE
    j = change.judge(r, [0.01] * 9, "2026-09-01")
    assert j["label"] == "inconclusive" and "clear" in j["reason"]
    half = pair(textured, lambda x, y: (255, 255, 255) if x < 8 else textured(x, y), b_scl=lambda x, y: 9 if x < 8 else 4)
    assert half["valid_share"] == 0.75 and half["score"] == 0                                    # the bright cloud never reached the score


def test_chip_quality_reads_cloud_and_nodata_from_the_classes():
    q = change.chip_quality(classes(lambda x, y: 9 if y < 8 else (0 if y < 12 else 4)))
    assert q == {"cloud_pct": 25.0, "nodata_pct": 12.5}


def test_judge_learns_before_it_flags_and_then_flags_only_a_jump():
    p = {"valid_share": 1.0, "score": 0.30, "changed_frac": 0.2}
    learning = change.judge(p, [0.03, 0.04], "2026-10-10")
    assert learning["label"] == "learning" and learning["n_obs"] == 2 and learning["z"] is None
    hist = [0.030, 0.034, 0.028, 0.032, 0.031, 0.036]
    assert change.judge(p, hist, "2026-09-01")["label"] == "changed"
    assert change.judge({**p, "score": 0.033}, hist, "2026-09-01")["label"] == "steady"


def test_every_verdict_carries_its_provenance():
    j = change.judge({"valid_share": 1.0, "score": 0.05, "changed_frac": 0.01}, [0.04] * 6, "2026-09-01")
    assert j["basis"] == "our_computation" and j["baseline_since"] == "2026-09-01" and j["n_obs"] == 6 and "not an interpretation" in j["method_note"]
    n = change.judge_night(20.0, [], None)
    assert n["basis"] == "our_computation" and n["baseline_since"] is None and n["n_obs"] == 0 and n["label"] == "learning"


def test_night_lights_flag_a_blackout_against_the_sites_own_nights():
    hist = [30.0, 31.0, 29.5, 30.5, 30.2, 29.8]
    assert change.judge_night(8.0, hist, "2026-09-01")["label"] == "dimmer"
    assert change.judge_night(30.4, hist, "2026-09-01")["label"] == "steady"
    assert change.judge_night(60.0, hist, "2026-09-01")["label"] == "brighter"


def test_night_stats_use_the_pictures_own_background():
    img = png.decode(png.encode(8, 8, 1, bytes([7] * 56 + [200] * 8)))
    s = change.night_stats(img)
    assert s["lit_share"] == 0.125 and s["mean"] == round((7 * 56 + 200 * 8) / 64, 3)


# ── the watch list ───────────────────────────────────────────────────────────────────────────
def plant(id_: str, name: str, lat: float, lon: float, **kw) -> Asset:
    return Asset(id=id_, name=name, type="power_plant", country="UA", lat=lat, lon=lon, precision=kw.pop("precision", "exact"), **kw)


def ev(asset_id: str, day: str, status: str, via: str = "") -> StatusEvent:
    return StatusEvent(id=event_id(asset_id, day, status, "MoD"), asset_id=asset_id, occurred_on=day, status=status, claimant="MoD", via=via)


@pytest.fixture
def ledger(tmp_path) -> Ledger:
    led = Ledger(tmp_path / "geo")
    led.add_assets([plant("a-old", "Old claim", 50.0, 30.0), plant("a-fresh", "Fresh confirmed", 49.0, 36.0), plant("a-city", "City level", 48.0, 35.0, precision="city_level"),
                    plant("a-quiet", "No events", 47.0, 34.0), plant("a-dev", "In the daily", 46.0, 33.0)])
    led.add_events([ev("a-old", "2026-09-25", "claimed_struck"), ev("a-fresh", "2026-10-16", "confirmed_damaged", "daily:2026-10-17:ukraine-russia-war"),
                    ev("a-fresh", "2026-10-12", "claimed_struck"), ev("a-city", "2026-10-17", "destroyed"), ev("a-quiet", "2026-07-01", "claimed_struck"),
                    ev("a-dev", "2026-10-17", "operational", "daily:2026-10-18:iran-us")])
    return led


def test_watch_list_comes_from_the_ledger_ranked_and_zones_sit_at_the_floor(ledger):
    sites = watchlist.build(ledger, NOW)
    ids = [s.id for s in sites]
    assert ids[0] == "a-fresh" and ids.index("a-fresh") < ids.index("a-dev") < ids.index("a-old")
    assert "a-city" not in ids and "a-quiet" not in ids                       # unplaced precision, and a strike outside the window
    zones = [s for s in sites if s.kind == "zone"]
    assert zones and all(s.priority == flags.ZONE_PRIORITY and s.half_km <= flags.ZONE_HALF_KM_MAX for s in zones)
    fresh = sites[0]
    assert fresh.event_on == "2026-10-12" and fresh.theater == "ukraine-russia-war" and fresh.asset_id == "a-fresh" and fresh.country == "UA"
    assert "in the daily's developments" in fresh.why
    assert next(s for s in sites if s.id == "a-dev").theater == "iran-us"


def test_bbox_is_a_square_around_the_point_and_wider_in_degrees_toward_the_pole():
    w, s, e, n = watchlist.bbox_of(60.0, 10.0, 2.5)
    assert abs((n - s) * 111.32 - 5.0) < 0.01 and abs((e - w) * 111.32 * 0.5 - 5.0) < 0.05


def test_rotation_takes_the_overdue_first_and_skips_the_recently_looked_at(ledger):
    sites = watchlist.build(ledger, NOW, zones=False)
    ts = NOW.timestamp()
    seen = {"a-fresh": ts - 3600, "a-old": ts - 200 * 3600}                    # fresh was looked at an hour ago; old is long overdue; dev never
    due = [s.id for s in watchlist.select_due(sites, seen, ts)]
    assert "a-fresh" not in due
    assert set(due) == {"a-old", "a-dev"}
    assert [s.id for s in watchlist.select_due(sites, seen, ts, limit=1)] == due[:1]


# ── a whole pass against a fake source ───────────────────────────────────────────────────────
class FakeImagery:
    """Three scenes over any place: before the strike (clear), after it (clear, a block of the ground changed) and a cloudy one."""

    def __init__(self) -> None:
        self.calls: list[str] = []
        self.scenes = [Scene("S2_20261015_T36", "2026-10-15", "2026-10-15T08:30:00Z", 3.0), Scene("S2_20261010_T36", "2026-10-10", "2026-10-10T08:30:00Z", 40.0),
                       Scene("S2_20261001_T36", "2026-10-01", "2026-10-01T08:30:00Z", 2.0)]

    def search(self, bbox, start, end):
        self.calls.append(f"search {start}..{end}")
        return [s for s in self.scenes if start <= s.date <= end]

    def rgb(self, scene, bbox):
        self.calls.append(f"rgb {scene.id}")
        return rgb_chip(lambda x, y: (250, 30, 30) if scene.date == "2026-10-15" and x < 10 and y < 10 else textured(x, y))

    def scl(self, scene, bbox):
        cloudy = scene.date == "2026-10-10"
        return scl_chip(lambda x, y: 9 if cloudy else 4)

    def night(self, bbox, day):
        self.calls.append(f"night {day}")
        return png.encode(8, 8, 1, bytes([7] * 48 + [180] * 16))


def test_a_pass_makes_a_before_after_pair_from_the_clearest_scenes(ledger):
    src = FakeImagery()
    out = run.run(src=src, ledger=ledger, now=NOW, do_publish=False)
    assert "a-fresh" in out["taken"] and out["states"]["a-fresh"] == "ok"
    e = next(s for s in store.read_json("doc.json")["sites"] if s["id"] == "a-fresh")
    assert e["baseline"]["date"] == "2026-10-01" and e["baseline"]["before_event"] is True        # clearest scene before the 12 Oct claim
    assert e["latest"]["date"] == "2026-10-15" and e["latest"]["local_cloud_pct"] == 0.0         # 10 Oct is cloudier: not chosen, though newer than the baseline
    assert e["change"]["score"] > 0.01 and e["change"]["changed_frac"] > 0.05
    assert e["change"]["label"] == "learning" and e["change"]["n_obs"] == 0                       # one look: honest about it
    assert e["night"]["date"] == "2026-10-14" and e["night"]["label"] == "learning"
    assert e["links"] == {"asset": "a-fresh", "country": "UA", "theater": "ukraine-russia-war"}
    assert any(c.startswith("search 2026-08-13..2026-10-11") for c in src.calls)                  # 60 days before the event for the baseline


def test_a_second_pass_on_the_same_scene_is_a_repeat_and_adds_no_observation(ledger):
    src = FakeImagery()
    run.run(src=src, ledger=ledger, now=NOW, do_publish=False, only=["a-fresh"])
    out = run.run(src=src, ledger=ledger, now=NOW + timedelta(days=2), do_publish=False, only=["a-fresh"])
    assert out["states"]["a-fresh"] == "repeat"
    recs = store.records("a-fresh")
    assert len(recs) == 2 and recs[0]["optical"]["state"] == "ok"                                 # append-only: both passes are on file
    assert sum(1 for c in src.calls if c.startswith("rgb")) == 2                                  # baseline + latest once; the repeat fetched no picture


def test_a_source_failure_is_recorded_for_the_site_and_does_not_stop_the_pass(ledger):
    from algent_backend.polite_http import SourceError

    class Down(FakeImagery):
        def search(self, bbox, start, end):
            raise SourceError("503")

    out = run.run(src=Down(), ledger=ledger, now=NOW, do_publish=False, limit=2)
    assert set(out["states"].values()) == {"error"} and len(out["taken"]) == 2


# ── publish shape ────────────────────────────────────────────────────────────────────────────
def test_publish_uploads_chips_before_the_document_and_the_document_names_only_those_chips(ledger):
    sent: list[str] = []

    def http(method, url, headers, body):
        sent.append(url.split("/published-assets/")[1])
        return 200

    run.run(src=FakeImagery(), ledger=ledger, now=NOW, only=["a-fresh"], do_publish=False)
    doc = store.read_json("doc.json")
    pub = run.publish(doc, http=http)
    assert pub["chips"]["ok"] and pub["chips"]["assets"] == 2
    chips = [k for k in sent if k.startswith("satellite/")]
    assert len(chips) == 2 and sent.index("live/satellite.json") > max(sent.index(c) for c in chips)
    assert sorted(chips) == sorted(document.chip_keys(doc))
    assert all(c.startswith("satellite/a-fresh/2026-10-") and c.endswith(".png") for c in chips)
    entry = next(s for s in doc["sites"] if s["id"] == "a-fresh")
    for block in (entry["change"], entry["night"]):
        assert block["basis"] == "our_computation" and block["method_note"] and "baseline_since" in block and "n_obs" in block
    assert "Copernicus Sentinel" in doc["credit"] and doc["counts"]["with_imagery"] == 1 and doc["v"] == 1


def test_a_failed_chip_upload_holds_the_document_back(ledger):
    run.run(src=FakeImagery(), ledger=ledger, now=NOW, only=["a-fresh"], do_publish=False)
    pub = run.publish(store.read_json("doc.json"), http=lambda *a: 500)
    assert not pub["chips"]["ok"] and "skipped" in pub["document"]
