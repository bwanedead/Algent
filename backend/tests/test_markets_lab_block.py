"""The "recipe lab" block of the track record: read defensively from the file the lab writes, additive to the document, never required."""

from __future__ import annotations

import json

import pytest

from algent_backend.contracts import shapes, spec
from algent_backend.experiment import calibrate
from algent_backend.markets import lab_block, score

BINS = [{"low": 0.0, "high": 0.2, "n": 16, "mean_p": 0.077, "hit_rate": 0.56}, {"low": 0.8, "high": 1.0, "n": 4, "mean_p": 0.9, "hit_rate": 0.75}]


@pytest.fixture(autouse=True)
def stores(tmp_path, monkeypatch):
    monkeypatch.setenv("ALGENT_EXPERIMENT_STORE", str(tmp_path / "lab"))
    monkeypatch.setenv("ALGENT_MARKETS_STORE", str(tmp_path / "markets"))
    (tmp_path / "lab").mkdir()


def put(tmp_path, doc) -> None:
    (tmp_path / "lab" / lab_block.FILE).write_text(json.dumps(doc) if not isinstance(doc, str) else doc, encoding="utf-8")


def test_no_file_or_a_broken_one_is_no_block_and_the_track_record_has_no_lab_key(tmp_path):
    assert lab_block.section() is None and "lab" not in score.track_record()
    for bad in ("{not json", "[]", json.dumps({"best": "nope", "live": {"raw": "x"}}), json.dumps({"best": {"raw": 0.1}})):
        put(tmp_path, bad)
        assert lab_block.section() is None


def test_the_lab_writes_the_block_the_markets_side_reads_and_the_document_still_fits_its_shape(tmp_path):
    board = {"protocols": {"x": {"name": "p0b", "policies": {"platt": {"n_fitted": 9, "raw": {"brier_minus_market": 0.13, "n_vs_market": 20, "bins": BINS},
                                                                       "calibrated": {"brier_minus_market": 0.06, "bins": BINS}}}}}}
    live = {"groups": {"all": {"raw": {"bins": BINS}, "calibrated": {"bins": BINS}}}, "headline": {"n": 300, "n_fitted": 250, "raw": 0.05, "calibrated": 0.02, "text": "if we had recalibrated ..."}}
    block = calibrate.track_block(board=board, live=live)
    assert block["best"]["protocol"] == "p0b" and block["best"]["raw"] == 0.13 and block["live"]["n"] == 300
    calibrate.write_block(block)
    sec = lab_block.section()
    assert sec["best"]["protocol"] == "p0b" and sec["best"]["n"] == 20 and sec["best"]["bins_raw"][0]["hit_rate"] == 0.56
    assert sec["live"]["calibrated"] == 0.02 and sec["live"]["text"].startswith("if we had recalibrated") and sec["live"]["n"] == 300
    doc = score.track_record()
    assert doc["schema"] == "ohmega.track-record/2" and doc["lab"] == sec
    assert spec.validate(doc, shapes.SHAPES["ohmega.track-record"]) == []


def test_junk_inside_a_good_block_is_dropped_not_passed_on(tmp_path):
    put(tmp_path, {"as_of": "t", "basis": "b", "best": {"protocol": "p", "n": 3, "n_fitted": 1, "raw": 0.2, "calibrated": 0.1, "bins_raw": [{"mean_p": "x", "hit_rate": 1}, *BINS * 20],
                                                         "bins_calibrated": "nope"}, "live": None})
    sec = lab_block.section()
    assert sec["live"] is None and len(sec["best"]["bins_raw"]) <= lab_block.MAX_BINS and sec["best"]["bins_calibrated"] == []
    assert all(isinstance(b["mean_p"], float) for b in sec["best"]["bins_raw"])
