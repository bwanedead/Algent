"""Live tiles: the density grid, the tile split, the index/etags, and the publish order (tiles before the index)."""

from __future__ import annotations

import pytest

pytestmark = pytest.mark.usefixtures("legacy_supabase")

import gzip
import json

import pytest

from algent_backend.live import flags, snapshots, tiles


@pytest.fixture(autouse=True)
def _env(tmp_path, monkeypatch):
    monkeypatch.setenv("ALGENT_LIVE_STORE", str(tmp_path / "live"))


def doc(rows, classes=("tanker", "cargo", "passenger", "fishing", "military", "other"), as_of="2026-10-12T10:00:00Z"):
    return {"v": 1, "as_of": as_of, "n": len(rows), "classes": list(classes), "counts": {}, "f": ["id", "lon", "lat", "hdg", "sog", "cls", "ts"], "rows": rows}


def row(i, lon, lat, cls=1):
    return [i, lon, lat, 90, 12.0, cls, 1000]


def test_cell_and_tile_ids_are_row_major_from_the_south_west():
    assert tiles.cell_id(-90, -180, 2) == 0 and tiles.cell_id(-89, -179, 2) == 0
    assert tiles.cell_id(-90, -178, 2) == 1                       # next column
    assert tiles.cell_id(-88, -180, 2) == 180                     # next row (360 / 2 columns)
    assert tiles.cell_id(90, 180, 2) == 90 * 180 - 1              # the poles / antimeridian clamp into the last cell
    assert tiles.tile_id(-90, -180, 10) == "r00c00"
    assert tiles.tile_id(26.5, 56.3, 10) == "r11c23"              # Hormuz: row floor(116.5 / 10), col floor(236.3 / 10)


def test_density_counts_by_class_and_drops_trailing_zeros():
    d = tiles.density(doc([row(1, 56.1, 26.1, 0), row(2, 56.9, 26.9, 0), row(3, 56.5, 26.5, 1), row(4, -40.0, -10.0, 5)]), 2)
    cells = {c[0]: c[1:] for c in d["cells"]}
    assert d["n"] == 4 and len(cells) == 2
    assert cells[tiles.cell_id(26.5, 56.5, 2)] == [2, 1]          # two tankers, one cargo; the rest trimmed
    assert cells[tiles.cell_id(-10.0, -40.0, 2)] == [0, 0, 0, 0, 0, 1]
    assert sum(sum(c[1:]) for c in d["cells"]) == d["n"]          # nothing lost, nothing double counted


def test_split_puts_every_row_in_exactly_one_tile_and_skips_empty_tiles():
    rows = [row(i, -170 + i * 7.3, -60 + i * 3.1) for i in range(40)]
    parts = tiles.split(doc(rows), 10)
    assert sum(t["n"] for t in parts.values()) == 40
    assert sorted(r[0] for t in parts.values() for r in t["rows"]) == list(range(40))
    for tid, t in parts.items():
        assert t["tile"] == tid and t["n"] == len(t["rows"]) > 0
        assert all(tiles.tile_id(r[2], r[1], 10) == tid for r in t["rows"])
    assert tiles.split(doc([]), 10) == {}


def test_build_makes_density_index_and_tiles_and_etags_follow_content(monkeypatch):
    v = doc([row(1, 56.1, 26.1, 0), row(2, 10.0, 54.0, 1)])
    a = doc([row(9, 2.3, 48.8, 0)], classes=("civil", "military", "tanker", "surveillance", "airlift", "fighter"))
    out = tiles.build(v, a)
    tid = tiles.tile_id(26.1, 56.1)
    assert {"density", "tiles/index", f"tiles/v/{tid}", f"tiles/a/{tiles.tile_id(48.8, 2.3)}"} <= set(out)
    idx = out["tiles/index"]
    assert idx["deg"] == flags.TILE_DEG and idx["as_of"] == v["as_of"]
    assert idx["vessels"][tid] == [1, tiles.etag(out[f"tiles/v/{tid}"])] and len(idx["vessels"]) == 2 and len(idx["aircraft"]) == 1
    assert out["density"]["deg"] == flags.DENSITY_DEG and set(out["density"]["layers"]) == {"vessels", "aircraft"}
    # a later cycle with the same positions but a new as_of: tiles (and so etags) are unchanged, only the index moves
    again = tiles.build({**v, "as_of": "2026-10-12T10:01:00Z"}, a)
    assert again[f"tiles/v/{tid}"] == out[f"tiles/v/{tid}"] and again["tiles/index"]["vessels"] == idx["vessels"]
    moved = tiles.build(doc([row(1, 56.2, 26.1, 0), row(2, 10.0, 54.0, 1)]), a)
    assert moved["tiles/index"]["vessels"][tid][1] != idx["vessels"][tid][1]


def test_tiles_are_small_next_to_the_full_document():
    rows = [row(i, -10 + (i % 300) * 0.05, 35 + (i // 300) * 0.05) for i in range(6000)]    # a dense European pile
    full = len(snapshots.encode_gz(doc(rows)))
    biggest = max(len(snapshots.encode_gz(t)) for t in tiles.split(doc(rows), 10).values())
    assert biggest < full                                                                     # a viewport never needs more than the world did
    assert len(snapshots.encode_gz(tiles.density(doc(rows)))) < full / 5


def test_publish_sends_tiles_before_the_index_and_gzips_the_new_documents(monkeypatch):
    monkeypatch.setenv("SUPABASE_URL", "https://x.supabase.co")
    monkeypatch.setenv("SUPABASE_SERVICE_ROLE_KEY", "k")
    sent = []

    def http(method, url, headers, body):
        sent.append(url.rsplit("/published-assets/", 1)[1])
        return 200

    out = tiles.build(doc([row(1, 56.1, 26.1, 0)]), doc([row(9, 2.3, 48.8, 0)]))
    res = snapshots.publish(out, http=http)
    assert res["ok"] and res["assets"] == len(out) == len(sent)
    assert max(i for i, k in enumerate(sent) if k.startswith("live/tiles/v/") or k.startswith("live/tiles/a/")) < sent.index("live/tiles/index.json.gz")
    assert "live/density.json.gz" in sent


def test_gzipped_density_round_trips():
    out = tiles.build(doc([row(1, 56.1, 26.1, 0)]), doc([]))
    assert json.loads(gzip.decompress(snapshots.encode_gz(out["density"])))["layers"]["vessels"]["n"] == 1
