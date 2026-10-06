"""Disputed and occupied territory on the daily maps: load, filter, status wording, drawing, back-compat."""

from __future__ import annotations

import re
from pathlib import Path

from algent_backend.agent_system.agents.intel import geo, geo_disputed
from algent_backend.agent_system.agents.intel.geo_layers import NO_LAYERS, load_layers

SAMPLE = Path(__file__).parent / "fixtures" / "geo" / "ne_disputed_sample.geojson"   # real features, vertices thinned


def _layers():
    find = lambda name: SAMPLE if name == "ne_10m_admin_0_disputed_areas.geojson" else None      # noqa: E731
    return load_layers(find, geo._RECOGNISED)


def _by_name(spec):
    return {d["name"]: d for d in spec["disputed"]}


def _sq(x0, y0, x1, y1):
    return [[[x0, y0], [x1, y0], [x1, y1], [x0, y1], [x0, y0]]]


def _land(name, iso, coords):
    return {"type": "Feature", "properties": {"NAME": name, "ADMIN": name, "ISO_A3": iso, "ISO_A2": iso[:2]},
            "geometry": {"type": "Polygon", "coordinates": coords}}


def _dev(lat, lon, country):
    return {"headline": "h", "when": "2026-10-04", "verification": "reported",
            "place": {"name": "Town", "country": country, "lat": lat, "lon": lon}}


def _crimea_spec():
    crimea = [[[33.0, 44.5], [36.0, 44.5], [36.0, 46.0], [33.0, 46.0], [33.0, 44.5]]]
    russia = {"type": "Feature", "properties": {"NAME": "Russia", "ADMIN": "Russia"},
              "geometry": {"type": "MultiPolygon", "coordinates": [_sq(37, 47, 60, 60), crimea]}}
    ukraine = _land("Ukraine", "UKR", _sq(24, 44, 40, 52))
    cs = geo.parse({"type": "FeatureCollection", "features": [russia, ukraine]})
    return geo.build_map([_dev(44.9, 34.1, "Ukraine")], cs, layers=_layers()), cs


def test_load_skips_ordinary_entries_and_keeps_claims_and_table_areas() -> None:
    names = {a.name for a in _layers().disputed}
    assert {"Crimea", "Gaza", "Golan Heights", "Hans Island", "Korean Demilitarized Zone (north)"} <= names
    assert "Israel" not in names and "Kosovo" not in names          # listed in the file, but no claim or table entry
    assert not any("﻿" in n for n in names)


def test_missing_file_degrades_to_no_layer() -> None:
    assert load_layers(lambda _n: None, geo._RECOGNISED).disputed == []
    assert NO_LAYERS.disputed == []


def test_status_table_wording_is_cited_and_factual() -> None:
    for key, st in geo_disputed.STATUS.items():
        assert st.source.startswith("https://") and st.text and st.label, key
        assert st.kind is None or st.kind in geo_disputed.KINDS, key
    crimea = geo_disputed.STATUS["Crimea"]
    assert "Ukrainian territory" in crimea.text and "occupied by Russia since 2014" in crimea.text
    assert "not a front line" in geo_disputed.STATUS["Luhansk People's Republic"].text


def test_fallback_uses_the_datasets_own_words_and_parses_claimants() -> None:
    (hans,) = [a for a in _layers().disputed if a.name == "Hans Island"]
    e = geo_disputed.entry(hans, [[[(10.0, 10.0), (60.0, 10.0), (60.0, 60.0), (10.0, 60.0)]]], 0.5)
    assert e["name"] == "Hans Island" and e["note"] == "Administered by Denmark; claimed by Canada"
    assert e["status"] == "administered" and e["claimants"] == ["Canada"] and e["source"] == ""
    assert geo_disputed.plain("Self admin.; Claimed by Azer.") == "Self-administered; claimed by Azerbaijan"
    assert geo_disputed.plain("Claimed by China, Taiwan, and Brunei") == "Claimed by China, Taiwan, and Brunei"


def test_entry_drops_specks_and_clips_to_frame() -> None:
    (crimea,) = [a for a in _layers().disputed if a.name == "Crimea"]
    assert geo_disputed.entry(crimea, [[[(1.0, 1.0), (2.0, 1.0), (2.0, 2.0), (1.0, 2.0)]]], 0.5) is None
    spec, _ = _crimea_spec()
    cr = _by_name(spec)["Crimea"]
    nums = [float(v) for v in re.findall(r"-?\d+(?:\.\d+)?", cr["d"])]
    assert min(nums) >= 0 and max(nums[0::2]) <= 1000 and max(nums[1::2]) <= spec["height"]
    assert 0 <= cr["x"] <= 1000 and cr["r"] > 0


def test_crimea_is_ukraine_with_the_occupied_hatch_on_top() -> None:
    spec, cs = _crimea_spec()
    assert geo.contains(geo.find_country(cs, "Ukraine"), 34.0, 45.0)                # base map: recognised borders
    assert not geo.contains(geo.find_country(cs, "Russia"), 34.0, 45.0)
    cr = _by_name(spec)["Crimea"]
    assert cr["status"] == "occupied" and "Ukrainian territory" in cr["note"] and cr["source"].startswith("https://")
    land = {c["name"] for c in spec["countries"]}
    assert "Ukraine" in land
    assert "Disputed areas: Natural Earth (public domain)." in spec["credit"]


def test_spec_without_the_layer_or_out_of_frame_is_a_plain_v2_map() -> None:
    cs = geo.parse({"type": "FeatureCollection", "features": [_land("Aland", "ALA", _sq(0, 0, 12, 12))]})
    for layers in (NO_LAYERS, _layers()):                       # no layer at all, and a layer whose areas are elsewhere
        spec = geo.build_map([_dev(6.0, 6.0, "Aland")], cs, layers=layers)
        assert spec["version"] == 2 and spec["disputed"] == [] and "Disputed areas" not in spec["credit"]
        for k in ("bbox", "countries", "points", "credit", "labels"):
            assert k in spec


def test_area_count_is_bounded() -> None:
    entries = [{"name": str(i), "area": float(i)} for i in range(30)]
    top = geo_disputed.top_areas(entries)
    assert len(top) == geo_disputed.MAX_AREAS and top[0]["name"] == "29" and "area" not in top[0]
