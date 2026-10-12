"""Live points: the compact world-zoom document (rounded positions + class), kept lossless in count, small next to the full one."""

from __future__ import annotations

import gzip
import json
import random

from algent_backend.live import points, snapshots, stream


def vessels(rows):
    return {"v": 1, "as_of": "2026-10-12T10:00:00Z", "n": len(rows), "classes": ["tanker", "cargo"], "counts": {"tanker": len(rows)}, "rows": rows}


def ship(i, lon, lat, cls=0, flag="NO", nf=0):
    return [i, lon, lat, 90, 12.0, cls, 1000, f"SHIP {i}", "OSLO", flag, nf]


def plane(i, lon, lat, cls=0):
    return [i, lon, lat, 90, 400.0, cls, 1000, "CALL", "A320", 30000]


def test_round_trip_rounds_to_five_hundredths_and_keeps_every_point():
    rows = [ship(1, 56.123, 26.531, 0), ship(2, 56.126, 26.534, 1), ship(3, -179.99, -89.98, 5), ship(4, 179.97, 89.96, 2)]
    got = points.decode(points.encode_points(vessels(rows), "vessels"))
    assert len(got) == 4                                            # duplicates and neighbours all stay: nothing is merged
    want = sorted((round(r[1] / 0.05) * 0.05, round(r[2] / 0.05) * 0.05, r[5]) for r in rows)
    assert sorted((round(lon / 0.05) * 0.05, round(lat / 0.05) * 0.05, c) for lon, lat, c, _ in got) == want


def test_notable_bit_and_class_survive():
    got = points.decode(points.encode_points(vessels([ship(1, 10.0, 10.0, 4, nf=1), ship(2, 11.0, 10.0, 1)]), "vessels"))
    assert sorted((c, n) for _, _, c, n in got) == [(1, False), (4, True)]
    air = points.decode(points.encode_points({"rows": [plane(1, 5.0, 5.0, 0), plane(2, 6.0, 5.0, 3)]}, "aircraft"))
    assert sorted((c, n) for _, _, c, n in air) == [(0, False), (3, True)]


def test_build_carries_totals_and_top_flags_without_ids_or_names():
    doc = points.build(vessels([ship(1, 1.0, 1.0, flag="NO"), ship(2, 2.0, 2.0, flag="NO"), ship(3, 3.0, 3.0, flag="PA")]),
                       {"as_of": "x", "n": 1, "classes": ["civil"], "counts": {}, "rows": [plane(9, 4.0, 4.0)]})
    v = doc["layers"]["vessels"]
    assert v["n"] == 3 and v["flags"] == [["NO", 2], ["PA", 1]] and len(v["p"]) == 9
    assert doc["layers"]["aircraft"]["n"] == 1 and "SHIP" not in json.dumps(doc) and doc["deg"] == 0.05


def test_points_are_a_small_fraction_of_the_full_document():
    rng = random.Random(7)
    rows = [ship(i, rng.uniform(-30, 40), rng.uniform(-10, 60), rng.randrange(6)) for i in range(20000)]
    full = len(gzip.compress(snapshots.encode(vessels(rows))))
    small = len(snapshots.encode_gz(points.build(vessels(rows), {"as_of": "x", "n": 0, "rows": []})))
    assert small < full / 4


def test_stream_publishes_points_and_gzips_them(monkeypatch, tmp_path):
    monkeypatch.setenv("ALGENT_LIVE_STORE", str(tmp_path / "live"))
    assert "points" in snapshots.GZIPPED
    from algent_backend.live import board, sky
    docs = stream.build_docs(board.VesselBoard(), sky.SkyBoard(), 1_800_000_000.0)
    assert docs["points"]["layers"]["vessels"]["n"] == 0 and "tiles/index" in docs
