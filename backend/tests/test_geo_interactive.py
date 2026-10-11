"""Interactive-map data contract: lon/lat on marks, unclipped disputed rings, live gates; and a land-coverage guard
(the Finland bug report: a concave country must stay land under any frame and either Natural Earth resolution)."""

from __future__ import annotations

import random
from pathlib import Path

import pytest

from algent_backend.agent_system.agents.intel import geo
from algent_backend.agent_system.agents.intel.geo_disputed import Disputed
from algent_backend.agent_system.agents.intel.geo_layers import Layers
from algent_backend.live import worldmap


def _feat(name, iso, coords):
    return {"type": "Feature", "properties": {"NAME": name, "ADMIN": name, "ISO_A3": iso, "ISO_A2": iso[:2]},
            "geometry": {"type": "Polygon", "coordinates": coords}}


# A concave, Finland-like country: a long gulf bites in from the south edge, a notch from the east.
_CONCAVE = [[(20, 59), (24, 59), (24, 62), (25, 62), (25, 59), (31, 59), (31, 70), (28, 70), (28, 64), (26, 64),
             (26, 70), (20, 70), (20, 59)]]


def _dev(lat, lon, country="Concavia"):
    return {"headline": "h", "when": "2026-10-01", "verification": "reported",
            "place": {"name": "Town", "country": country, "lat": lat, "lon": lon}}


def _inside(x, y, ring):
    ins, j = False, len(ring) - 1
    for i, (xi, yi) in enumerate(ring):
        xj, yj = ring[j]
        if (yi > y) != (yj > y) and x < (xj - xi) * (y - yi) / (yj - yi) + xi:
            ins = not ins
        j = i
    return ins


def _rings(d):
    return [[tuple(map(float, p.split())) for p in sub.rstrip("Z").split("L")] for sub in d.split("M")[1:]]


def _coverage_misses(countries, name, samples, frames):
    """How many sample points inside ``name`` (lon, lat) fall in no drawn ring, over the given event frames."""
    misses = 0
    for pts in frames:
        m = geo.build_map([_dev(la, lo, "sea") for lo, la in pts], countries, layers=geo.NO_LAYERS)
        w, s, e, n = m["bbox"]
        drawn = [r for c in m["countries"] if c["name"] == name for r in _rings(c["d"])]
        for lo, la in samples:
            if w < lo < e and s < la < n:
                x, y = (lo - w) / (e - w) * m["width"], (n - la) / (n - s) * m["height"]
                if sum(_inside(x, y, r) for r in drawn) % 2 == 0:
                    misses += 1
    return misses


def test_marks_carry_lon_lat_and_annotations_too() -> None:
    cs = geo.parse({"features": [_feat("Concavia", "CCC", _CONCAVE)]})
    m = geo.build_map([_dev(65.0, 22.0)], cs, layers=geo.NO_LAYERS)
    p = m["points"][0]
    assert (p["lon"], p["lat"]) == (22.0, 65.0)
    w, s, e, n = m["bbox"]                                   # the SVG x/y and lon/lat agree (equirectangular frame)
    assert p["x"] == pytest.approx((22.0 - w) / (e - w) * m["width"], abs=0.1)
    assert p["y"] == pytest.approx((n - 65.0) / (n - s) * m["height"], abs=0.1)


def test_disputed_rings_are_unclipped_lon_lat_polygons() -> None:
    cs = geo.parse({"features": [_feat("Concavia", "CCC", _CONCAVE)]})
    zone = Disputed("Test zone", "Claimed by Concavia", [[[(22.0, 60.0), (40.0, 60.0), (40.0, 66.0), (22.0, 66.0)]]],
                    (22.0, 60.0, 40.0, 66.0))
    m = geo.build_map([_dev(65.0, 22.5)], cs, layers=Layers(disputed=[zone]))
    ring = m["disputed"][0]["rings"][0][0]
    assert max(lon for lon, _ in ring) == 40.0                # runs past the frame edge: panning shows no cut
    assert m["bbox"][2] < 40.0


def test_concave_country_stays_land_under_any_frame() -> None:
    cs = geo.parse({"features": [_feat("Concavia", "CCC", _CONCAVE)]})
    rnd = random.Random(7)
    samples = [(rnd.uniform(20, 31), rnd.uniform(59, 70)) for _ in range(400)]
    samples = [p for p in samples if geo.contains(cs[0], *p)]
    frames = [[(rnd.uniform(18, 32), rnd.uniform(58, 71)) for _ in range(rnd.randint(1, 3))] for _ in range(40)]
    assert _coverage_misses(cs, "Concavia", samples, frames) == 0


@pytest.mark.parametrize("fname", ["ne_50m_admin_0_countries.geojson", "ne_110m_admin_0_countries.geojson"])
def test_finland_is_land_in_real_data(fname) -> None:
    path = geo.find_file(fname)
    if path is None:
        pytest.skip("Natural Earth file not on this machine")
    cs = geo.load(Path(path))
    fi = next(c for c in cs if c.name == "Finland")
    rnd = random.Random(1)
    samples = [(rnd.uniform(21, 31.5), rnd.uniform(60, 70)) for _ in range(300)]
    samples = [p for p in samples if geo.contains(fi, *p)]
    frames = [[(rnd.uniform(15, 30) + rnd.uniform(-6, 6), rnd.uniform(58, 69) + rnd.uniform(-3, 3))] for _ in range(25)]
    assert _coverage_misses(cs, "Finland", samples, frames) == 0


def test_world_document_publishes_the_counting_lines(monkeypatch) -> None:
    cs = geo.parse({"features": [_feat("Concavia", "CCC", _CONCAVE)]})
    monkeypatch.setattr(worldmap.places, "_countries", lambda: cs)
    doc = worldmap.build()
    assert doc is not None and {g["region"] for g in doc["gates"]} >= {"hormuz", "suez"}
    hormuz = next(g for g in doc["gates"] if g["region"] == "hormuz")
    assert len(hormuz["a"]) == 2 and len(hormuz["b"]) == 2
