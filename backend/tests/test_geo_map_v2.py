"""Map spec v2: simplification, scale bar, city density, chokepoint annotations, old-path compatibility, Crimea."""

from __future__ import annotations

import math
import re
from datetime import date, timedelta

import pytest

from algent_backend.agent_system.agents.intel import geo, geo_draw, geo_layers
from algent_backend.agent_system.agents.intel.geo_layers import City, Layers
from algent_backend.instruments import store
from algent_backend.instruments.contracts import Observation


def _feat(name, iso, coords):
    return {"type": "Feature", "properties": {"NAME": name, "ADMIN": name, "ISO_A3": iso, "ISO_A2": iso[:2]},
            "geometry": {"type": "Polygon", "coordinates": coords}}


def _sq(x0, y0, x1, y1):
    return [[[x0, y0], [x1, y0], [x1, y1], [x0, y1], [x0, y0]]]


def _dev(lat, lon, country="Aland"):
    return {"headline": "h", "when": "2026-09-28", "verification": "reported",
            "place": {"name": "Town", "country": country, "lat": lat, "lon": lon}}


def test_simplify_stays_within_tolerance_and_keeps_ends() -> None:
    line = [(float(i), 0.3 * math.sin(i / 3.0)) for i in range(200)]
    for tol in (0.05, 0.5):
        kept = geo_draw.simplify(line, tol)
        assert kept[0] == line[0] and kept[-1] == line[-1] and len(kept) < len(line)
        for x, y in line:                              # every dropped vertex is within tol of the simplified line
            d = min(_seg_dist((x, y), a, b) for a, b in zip(kept, kept[1:], strict=False))
            assert d <= tol + 1e-9
    ring = [(0.0, 0.0), (5.0, 0.01), (10.0, 0.0), (10.0, 10.0), (0.0, 10.0)]
    out = geo_draw.simplify(ring, 0.1, closed=True)
    assert (5.0, 0.01) not in out and len(out) == 4          # a near-collinear vertex goes, the corners stay


def _seg_dist(p, a, b):
    ax, ay, bx, by, px, py = *a, *b, *p
    dx, dy = bx - ax, by - ay
    t = 0.0 if dx == dy == 0 else max(0.0, min(1.0, ((px - ax) * dx + (py - ay) * dy) / (dx * dx + dy * dy)))
    return math.hypot(ax + t * dx - px, ay + t * dy - py)


def test_tolerance_grows_with_the_frame_and_is_capped() -> None:
    assert geo.simplify_tolerance(12) == pytest.approx(0.6)
    assert geo.simplify_tolerance(48) > geo.simplify_tolerance(12)
    assert geo.simplify_tolerance(360) == geo.MAX_TOLERANCE


def test_scale_bar_is_a_round_number_true_at_mid_latitude() -> None:
    bar = geo_draw.scale_bar(0.0, 10.0, 0.0, 1000.0)             # 10 deg at the equator = 1113.2 km
    assert bar["km"] == 200 and bar["label"] == "200 km"
    assert bar["px"] == pytest.approx(200 / (1113.2 / 1000), abs=0.1)
    high = geo_draw.scale_bar(0.0, 10.0, 60.0, 1000.0)           # cos(60) = 0.5: half the ground per degree
    assert high["km"] == 100
    assert geo_draw.nice_km(740) == 500 and geo_draw.nice_km(1999) == 1000 and geo_draw.nice_km(0.4) == 0.2


def _cities(n=40):
    return [City(f"C{i}", 1.0 + (i % 8) * 1.2, 1.0 + (i // 8) * 1.2, 1_000_000 - i * 1000, i == 39, "Aland")
            for i in range(n)]


def test_city_density_adapts_and_capitals_are_always_kept() -> None:
    layers = Layers(cities=_cities())
    close, wide = (0.0, 0.0, 12.0, 12.0), (-60.0, -60.0, 60.0, 60.0)
    proj_c = lambda lon, lat: (lon / 12 * 1000, (12 - lat) / 12 * 1000)           # noqa: E731
    proj_w = lambda lon, lat: ((lon + 60) / 120 * 1000, (60 - lat) / 120 * 1000)   # noqa: E731
    near = geo_layers.select_cities(layers, proj_c, close, 1000, 1000, 12)
    far = geo_layers.select_cities(layers, proj_w, wide, 1000, 1000, 120)
    assert any(c["capital"] for c in near) and any(c["capital"] for c in far)        # C39 is the capital
    assert len([c for c in far if not c["capital"]]) < len([c for c in near if not c["capital"]])
    pts = [(c["x"], c["y"]) for c in near if not c["capital"]]
    assert all(math.hypot(a[0] - b[0], a[1] - b[1]) >= geo_layers.CITY_SPACING for i, a in enumerate(pts) for b in pts[:i])
    assert near[0]["capital"]                                                       # capitals lead the priority order


def _stock(series_id, today: date, now: float, year_ago: float) -> None:
    obs = [Observation(series_id=series_id, period=(today - timedelta(days=d)).isoformat(), value=v, fetched_at="x", source_url="u")
           for d, v in ((0, now), (1, now), (7, now), (30, now), (365, year_ago), (366, year_ago))]
    store.append(series_id, obs)


@pytest.fixture()
def gulf(monkeypatch, tmp_path):
    monkeypatch.setenv("ALGENT_INSTRUMENTS_STORE", str(tmp_path / "istore"))
    return geo.parse({"type": "FeatureCollection", "features": [_feat("Aland", "ALA", _sq(50, 20, 62, 32))]})


def test_chokepoint_annotation_present_with_stored_public_reading(gulf) -> None:
    today = date.today() - timedelta(days=3)
    _stock("chk_hormuz_transits", today, 1.0, 102.0)
    spec = geo.build_map([_dev(26.0, 56.0)], gulf, layers=geo.NO_LAYERS)
    (note,) = spec["annotations"]
    assert note["title"] == "Strait of Hormuz" and note["lines"][0] == "1 ship/day · 102 a year ago"
    assert note["lines"][1] == f"as of {today.day} {today:%b}"
    assert 0 <= note["x"] <= 1000 and 0 <= note["y"] <= spec["height"]
    assert "IMF PortWatch" in spec["credit"]


def test_chokepoint_annotation_absent_when_store_empty_or_outside_frame(gulf) -> None:
    assert geo.build_map([_dev(26.0, 56.0)], gulf, layers=geo.NO_LAYERS)["annotations"] == []
    _stock("chk_suez_transits", date.today(), 30.0, 40.0)                       # stored, but Suez is not in this frame
    spec = geo.build_map([_dev(26.0, 56.0)], gulf, layers=geo.NO_LAYERS)
    assert spec["annotations"] == [] and "PortWatch" not in spec["credit"]


def test_non_public_series_is_never_annotated(gulf, monkeypatch) -> None:
    from algent_backend.instruments import catalog
    _stock("chk_hormuz_transits", date.today(), 1.0, 102.0)
    monkeypatch.setitem(catalog._BY_ID, "chk_hormuz_transits", catalog._BY_ID["chk_hormuz_transits"].model_copy(update={"public_display": False}))
    monkeypatch.setattr(catalog, "CATALOG", [catalog._BY_ID[s.id] for s in catalog.CATALOG])
    assert geo.build_map([_dev(26.0, 56.0)], gulf, layers=geo.NO_LAYERS)["annotations"] == []


def test_v2_spec_shape_and_v1_keys_unchanged(gulf) -> None:
    spec = geo.build_map([_dev(26.0, 56.0)], gulf, layers=geo.NO_LAYERS)
    assert spec["version"] == 2
    for k in ("bbox", "projection", "width", "height", "countries", "points", "credit"):    # what a v1 reader needs
        assert k in spec
    assert spec["scale"]["km"] > 0 and spec["locator"]["rect"]["w"] >= 3 and spec["labels"][0]["name"] == "Aland"
    assert spec["labels"][0]["key"] is True
    nums = [float(v) for v in re.findall(r"-?\d+(?:\.\d+)?", spec["countries"][0]["d"])]
    assert max(nums[0::2]) <= 1000 and max(nums[1::2]) <= spec["height"]


def test_missing_50m_falls_back_to_110m(tmp_path, monkeypatch) -> None:
    (tmp_path / "ne_110m_admin_0_countries.geojson").write_text('{"type":"FeatureCollection","features":[]}', encoding="utf-8")
    monkeypatch.delenv("ALGENT_NATURAL_EARTH", raising=False)
    monkeypatch.setattr(geo, "_bases", lambda: [tmp_path.parent / "x"])
    monkeypatch.setattr(geo, "_NE_DIR", (tmp_path.name,))
    monkeypatch.setattr(geo, "_bases", lambda: [tmp_path.parent])
    assert geo.default_path().name == "ne_110m_admin_0_countries.geojson"
    (tmp_path / "ne_50m_admin_0_countries.geojson").write_text("{}", encoding="utf-8")
    assert geo.default_path().name == "ne_50m_admin_0_countries.geojson"


def test_crimea_is_drawn_as_ukraine_in_cities_and_land() -> None:
    crimea = [[[33.0, 44.5], [36.0, 44.5], [36.0, 46.0], [33.0, 46.0], [33.0, 44.5]]]
    russia = {"type": "Feature", "properties": {"NAME": "Russia", "ADMIN": "Russia"},
              "geometry": {"type": "MultiPolygon", "coordinates": [_sq(37, 47, 60, 60), crimea]}}
    ukraine = _feat("Ukraine", "UKR", _sq(24, 47, 36, 52))
    cs = geo.parse({"type": "FeatureCollection", "features": [russia, ukraine]})
    assert geo.contains(geo.find_country(cs, "Ukraine"), 34.0, 45.0) and not geo.contains(geo.find_country(cs, "Russia"), 34.0, 45.0)
    assert geo.default_layers is not None


def test_a_far_stray_point_is_left_off_and_named():
    """One US point in a Russia–Ukraine section must not stretch the frame across the world."""
    from algent_backend.agent_system.agents.intel import geo
    pts = [(30.5, 50.4), (36.2, 50.0), (37.8, 48.0), (33.4, 44.9), (-77.0, 38.9)]
    assert geo._off_map(pts) == {4}
    assert geo._off_map(pts[:4]) == set()              # a normal theater keeps every point
    assert geo._off_map([(30.5, 50.4), (-77.0, 38.9)]) == set()   # two points: no way to tell the stray
