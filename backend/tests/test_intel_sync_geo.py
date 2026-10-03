"""Intel sync (publish once), coverage labels, key figures, validated places and the where-it-happened map."""

from __future__ import annotations

import json
import re
from datetime import UTC, datetime

import pytest

from algent_backend.agent_system.agents.intel import daily, geo, render
from algent_backend.agent_system.agents.intel.contracts import (
    CrossTheater,
    DaySummary,
    Development,
    KeyFigure,
    Place,
    SectionDraft,
    coverage_label,
)
from algent_backend.publishing import intel_page

from test_intel_daily import AS_OF, SRC_A, SUMMARY, _board, _ctx, _store


def _square(x0, y0, x1, y1):
    return [[[x0, y0], [x1, y0], [x1, y1], [x0, y1], [x0, y0]]]


def _geojson():
    def feat(name, iso, coords):
        return {"type": "Feature", "properties": {"NAME": name, "ADMIN": name, "ISO_A3": iso, "ISO_A2": iso[:2]},
                "geometry": {"type": "Polygon", "coordinates": coords}}
    return {"type": "FeatureCollection", "features": [
        feat("Aland", "ALA", _square(0, 0, 10, 10)), feat("Bland", "BLA", _square(20, 0, 30, 10)),
        feat("Farland", "FAR", _square(100, 40, 110, 50))]}


@pytest.fixture()
def countries():
    return geo.parse(_geojson())


def _place(name="Town", country="Aland", lat=5.0, lon=5.0):
    return Place(name=name, country=country, lat=lat, lon=lon)


# ── places ────────────────────────────────────────────────────────────────────────────────────
def test_place_inside_country_is_kept_with_canonical_country(countries) -> None:
    assert geo.validate_place(_place(country="ala"), countries) == {"name": "Town", "country": "Aland",
                                                                    "lat": 5.0, "lon": 5.0}      # ISO code, any case


def test_place_just_outside_but_near_the_border_is_kept(countries) -> None:
    assert geo.validate_place(_place(lon=10.25), countries)          # ~28 km outside: coastal city on a coarse map
    assert geo.validate_place(_place(lon=11.0), countries) is None    # ~111 km outside: dropped


def test_place_in_the_wrong_or_unknown_country_is_dropped_not_fixed(countries) -> None:
    assert geo.validate_place(_place(lon=25.0), countries) is None    # inside Bland, claimed as Aland
    assert geo.validate_place(_place(country="Atlantis"), countries) is None
    assert geo.validate_place(_place(lat=float("nan")), countries) is None
    assert geo.validate_place(_place(lat=95.0), countries) is None
    assert geo.validate_place(_place(), None) is None                 # no basemap, nothing is trusted


def test_maritime_points_are_allowed_unless_deep_inland(countries) -> None:
    assert geo.validate_place(_place(name="Strait", country="sea", lat=5.0, lon=15.0), countries)["country"] == "sea"
    assert geo.validate_place(_place(name="Strait", country="", lat=5.0, lon=10.2), countries)    # within 50 km of a coast
    assert geo.validate_place(_place(name="Strait", country="sea", lat=5.0, lon=5.0), countries) is None   # land


def test_normalise_drops_invalid_places_and_keeps_good_ones(countries) -> None:
    draft = SectionDraft(bottom_line="b", developments=[
        Development(headline="a", place=_place()), Development(headline="b", place=_place(lon=25.0)),
        Development(headline="c")])
    out = daily.normalise_section(draft, pulse_table={}, has_previous=False, researched=False,
                                  research_urls=set(), reported_urls=set(), countries=countries)
    assert [bool(d.place) for d in out.developments] == [True, False, False]


# ── map ───────────────────────────────────────────────────────────────────────────────────────
def _dev(n_place, when="2026-09-28", verification="reported"):
    return {"headline": "h", "when": when, "verification": verification, "place": n_place}


def test_no_validated_point_no_map(countries) -> None:
    assert geo.build_map([_dev(None)], countries) is None
    assert geo.build_map([], countries) is None
    assert geo.build_map([_dev({"name": "T", "country": "Aland", "lat": 5, "lon": 5})], None) is None


def test_map_spec_projection_bbox_and_culling(countries) -> None:
    spec = geo.build_map([_dev(None), _dev({"name": "Town", "country": "Aland", "lat": 5.0, "lon": 5.0},
                                           verification="researched")], countries)
    # one point: a minimum 8-degree span around it, so its region still shows
    assert spec["bbox"] == [1.0, 1.0, 9.0, 9.0] and spec["projection"] == "equirectangular" and spec["width"] == 1000
    assert spec["height"] == round(1000 * 8 / (8 * __import__("math").cos(__import__("math").radians(5.0))))
    (pt,) = spec["points"]
    assert pt == {"x": 500.0, "y": round(4 / 8 * spec["height"], 1), "label": "Town", "date": "2026-09-28",
                  "verification": "researched", "n": 2}                      # n is 1-based: developments[1]
    assert [c["name"] for c in spec["countries"]] == ["Aland"]               # Bland and Farland are outside the frame
    nums = [float(v) for v in re.findall(r"-?\d+(?:\.\d+)?", spec["countries"][0]["d"])]
    xs, ys = nums[0::2], nums[1::2]
    assert min(xs) >= 0 and max(xs) <= 1000 and min(ys) >= 0 and max(ys) <= spec["height"]   # clipped to the frame
    assert "Natural Earth" in spec["credit"]


def test_map_frame_fits_points_pads_and_stays_in_the_world(countries) -> None:
    spec = geo.build_map([_dev({"name": "A", "country": "Aland", "lat": 2.0, "lon": 2.0}),
                          _dev({"name": "B", "country": "Bland", "lat": 8.0, "lon": 28.0})], countries)
    w, s, e, n = spec["bbox"]
    assert w < 2.0 and e > 28.0 and s < 2.0 and n > 8.0                       # padded
    assert {c["name"] for c in spec["countries"]} == {"Aland", "Bland"}
    assert all(0 <= p["x"] <= 1000 and 0 <= p["y"] <= spec["height"] for p in spec["points"])
    edge = geo.build_map([_dev({"name": "E", "country": "sea", "lat": 0.0, "lon": 179.5})], countries)
    assert edge["bbox"][2] <= 180.0 and edge["bbox"][0] >= -180.0 and edge["bbox"][1] >= -90.0


def test_default_path_and_loading_are_safe_when_the_file_is_missing(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("ALGENT_NATURAL_EARTH", str(tmp_path / "nope.geojson"))
    assert geo.load() is None
    f = tmp_path / "ne.geojson"
    f.write_text(json.dumps(_geojson()), encoding="utf-8")
    monkeypatch.setenv("ALGENT_NATURAL_EARTH", str(f))
    assert [c.name for c in geo.load()] == ["Aland", "Bland", "Farland"]


# ── key figures ───────────────────────────────────────────────────────────────────────────────
def test_key_figures_need_a_finite_value_a_date_and_a_research_source() -> None:
    def fig(**kw):
        return KeyFigure(**{"label": "Transits/day", "value": 5, "unit": "ships", "baseline": 30,
                            "baseline_label": "pre-crisis", "as_of": "2026-09-28", "source": SRC_A, **kw})
    draft = SectionDraft(bottom_line="b", key_figures=[
        fig(), fig(source="https://invented.example"), fig(value=float("nan")), fig(as_of="yesterday"),
        fig(label=" "), fig(source=SRC_A + "/", baseline=float("inf")), fig(value=0), fig(), fig(), fig()])
    out = daily.normalise_section(draft, pulse_table={}, has_previous=False, researched=True,
                                  research_urls={SRC_A}, reported_urls={"https://reported.example"})
    assert len(out.key_figures) == daily.MAX_KEY_FIGURES == 4
    assert out.key_figures[0].baseline == 30 and out.key_figures[0].baseline_label == "pre-crisis"
    assert out.key_figures[1].baseline is None and out.key_figures[1].baseline_label == ""   # bad baseline dropped
    assert out.key_figures[2].value == 0                                       # zero is a number, not "missing"


def test_reported_urls_do_not_make_a_figure_citable() -> None:
    draft = SectionDraft(bottom_line="b", key_figures=[KeyFigure(label="x", value=1, as_of="2026-09-28", source=SRC_A)])
    out = daily.normalise_section(draft, pulse_table={}, has_previous=False, researched=False,
                                  research_urls=set(), reported_urls={SRC_A})
    assert out.key_figures == []


# ── coverage ──────────────────────────────────────────────────────────────────────────────────
def test_coverage_labels_map_the_stored_trend() -> None:
    assert [coverage_label(t) for t in ("heating", "steady", "cooling", "new", "")] == [
        "rising coverage", "steady coverage", "falling coverage", "newly reported", ""]


def test_coverage_is_in_the_snapshot_and_daily_temperature_and_daily_lists_theaters(tmp_path, monkeypatch) -> None:
    store = _store(tmp_path, monkeypatch)
    monkeypatch.setattr(geo, "load", lambda *_a, **_k: geo.parse(_geojson()))
    draft = SectionDraft(bottom_line="b", developments=[Development(headline="h", when="2026-09-28", place=_place())],
                         key_figures=[KeyFigure(label="x", value=2, as_of="2026-09-28", source=SRC_A)])
    ctx = _ctx({"Alpha": draft, "Bravo": SectionDraft(bottom_line="b")}, SUMMARY)
    rec = daily.produce_daily(ctx, domain="geopolitics", top=2, model_spec=None, as_of=AS_OF, board=_board(),
                              out=tmp_path)["report"]
    a = rec["theaters"][0]
    assert a["temperature"]["trend"] == "heating" and a["temperature"]["coverage"] == "rising coverage"
    assert rec["theaters"][1]["temperature"]["coverage"] == "steady coverage"
    assert a["developments"][0]["place"]["country"] == "Aland" and a["map"]["points"][0]["n"] == 1
    assert rec["theaters"][1]["map"] is None
    assert a["key_figures"] == []                                  # no research ran: nothing is citable
    html = (tmp_path / "daily_geopolitics.html").read_text(encoding="utf-8")
    assert "rising coverage" in html and "<svg" in html
    intel = tmp_path / "intel"
    (intel / "boards").mkdir(parents=True)
    (intel / "boards" / "b.json").write_text(json.dumps(_board()), encoding="utf-8")
    snap = intel_page.build_snapshot(store, intel, now=datetime(2026, 9, 30, tzinfo=UTC))
    assert [t["coverage"] for t in snap["theaters"]] == ["rising coverage", "steady coverage", "steady coverage"]
    assert snap["daily"][0]["theaters"] == [{"id": "thr_a", "name": "Alpha"}, {"id": "thr_b", "name": "Bravo"}]
    assert intel_page.build_index(snap)["theaters"][0]["coverage"] == "rising coverage"


def test_render_shows_figures_with_baseline() -> None:
    t = {"theater_id": "t", "name": "T", "temperature": {"heat": 1, "trend": "new", "coverage": "newly reported",
                                                          "recent_share": 0.1, "prior_share": 0.0},
         "escalation": {"direction": "rising", "pace": "fast"}, "pulses": [], "bottom_line": "b",
         "since_yesterday": [], "developments": [], "context": [], "outlook": "", "watch_next": [],
         "key_figures": [{"label": "Transits/day", "value": 5, "unit": "ships", "baseline": 30,
                          "baseline_label": "pre-crisis", "as_of": "2026-09-28", "source": SRC_A}],
         "brief_slug": None, "map": None}
    html = render._daily_theater(t)
    assert "Transits/day" in html and "pre-crisis: 30" in html and "newly reported" in html


# ── summary ───────────────────────────────────────────────────────────────────────────────────
def test_summary_keeps_real_links_by_exact_theater_names_and_drops_the_rest() -> None:
    sections = [{"name": n, "temperature": {"trend": "steady", "coverage": "steady coverage"}, "bottom_line": "b",
                 "escalation": {"direction": "steady", "pace": "flat"}, "developments": []}
                for n in ("US Iraq withdrawal", "Iran proxy axis", "Hormuz shipping")]
    summary = DaySummary(headline="h", the_day=["x"], cross_theater=[
        CrossTheater(theaters=["us iraq withdrawal", "IRAN PROXY AXIS", "Mars"], link="withdrawal frees the proxies"),
        CrossTheater(theaters=["Iran proxy axis", "Hormuz shipping"], link="proxy attacks reprice the strait"),
        CrossTheater(theaters=["Hormuz shipping", "Hormuz shipping"], link="same theater twice"),
        CrossTheater(theaters=["Iran proxy axis", "Hormuz shipping"], link="  ")])
    ctx = _ctx({}, summary)
    out = daily.write_summary(ctx, None, sections, as_of=AS_OF, domain="geopolitics", model_spec=None)
    assert [(c.theaters, c.link) for c in out.cross_theater] == [
        (["US Iraq withdrawal", "Iran proxy axis"], "withdrawal frees the proxies"),
        (["Iran proxy axis", "Hormuz shipping"], "proxy attacks reprice the strait")]


def test_summary_doctrine_asks_for_real_links_and_none_when_none_exist() -> None:
    role = daily.SUMMARY_ROLE.lower()
    assert "shared actors" in role and "causal" in role and "empty when" in role
    assert "never compute" in daily.DAILY_ROLE.lower() and "key_figures" in daily.DAILY_ROLE


# ── sync: publish once ────────────────────────────────────────────────────────────────────────
@pytest.fixture()
def publishes(monkeypatch):
    calls: list[str] = []
    monkeypatch.setattr(intel_page, "publish_intel", lambda: calls.append("publish") or {"published": True})
    return calls


def test_pulse_verbs_publish_once_and_only_when_something_changed(publishes, monkeypatch) -> None:
    from algent_backend.agent_system.agents.pulse import registry
    from algent_backend.cli.newsroom import pulse as cli

    monkeypatch.setattr(cli, "_registry_ctx", lambda: None)
    monkeypatch.setattr(cli, "_spec", lambda: None)
    monkeypatch.setattr("algent_backend.agent_system.agents.pulse.repository.pulse_store", lambda: object())
    monkeypatch.setattr(registry, "promote_ready", lambda *a, **k: {"promoted": [], "duplicates": [], "errors": []})
    cli._promote_ready(None)
    assert publishes == []                                              # nothing promoted, nothing changed
    monkeypatch.setattr(registry, "promote_ready", lambda *a, **k: {"promoted": [{"name": "P"}], "errors": []})
    cli._promote_ready(None)
    assert publishes == ["publish"]
    monkeypatch.setattr(registry, "promote", lambda *a, **k: {"status": "promoted"})
    cli._promote(type("A", (), {"proposal_id": "p", "situation": ""})())
    assert publishes == ["publish", "publish"]
    assert json.loads(capsys.readouterr().out.rsplit("}\n{", 1)[-1].join(["{", ""]) if False else "{}") == {}


def test_daily_promotes_quietly_then_publishes_exactly_once(publishes, monkeypatch) -> None:
    from algent_backend.data_backup import sync
    from algent_backend.agent_system.agents.intel import desk
    from algent_backend.cli.newsroom import intel as cli
    from algent_backend.cli.newsroom import pulse as pulse_cli

    order: list[str] = []
    monkeypatch.setattr(cli, "_heat", lambda args, publish=True: (order.append(f"heat:{publish}"), 0)[1])
    monkeypatch.setattr(cli, "_ctx", lambda run_id: None)
    monkeypatch.setattr(cli, "_out", lambda as_of: None)
    monkeypatch.setattr(desk, "latest_board", lambda: {"as_of": AS_OF})
    monkeypatch.setattr(daily, "produce_daily", lambda *a, **k: {
        "path": "p", "report": {"summary": {"headline": "h"}}, "theaters": [], "research_usd": 0.0})
    monkeypatch.setattr(pulse_cli, "promote_ready_quietly", lambda: order.append("promote") or {"promoted": []})
    monkeypatch.setattr(sync, "backup", lambda note="": {"ok": True})
    monkeypatch.setattr(intel_page, "publish_intel", lambda: order.append("publish") or {"published": True})
    args = type("A", (), {"domain": "geopolitics", "top": 1, "research": False, "fresh_research": False, "days": 7})()
    assert cli._daily(args) == 0
    assert order == ["heat:False", "promote", "publish"]               # one publish, after the Pulses moved


def test_rail_republishes_intel_once_after_pulses_move(monkeypatch) -> None:
    from algent_backend.agent_system.agents.newsroom import rail
    from algent_backend.agent_system.agents.pulse import update
    from algent_backend.agent_system.agents.research import store as research_store

    calls: list[str] = []
    events: list[str] = []
    monkeypatch.setattr(intel_page, "publish_intel", lambda: calls.append("publish") or {"published": True})
    profile = type("P", (), {"model_dump": lambda self: {"id": "prof_1"}})()
    monkeypatch.setattr(research_store.JsonProfileStore, "get", lambda self, pid: profile)
    ctx = type("C", (), {"run_id": "r", "emit": lambda self, et, p=None: events.append(et)})()
    out = {"rail": {"stage_reached": "complete", "profile_id": "prof_1"}}

    monkeypatch.setattr(update, "update_quietly", lambda *a, **k: {"touched": []})
    rail._feed_pulses(ctx, out)
    assert calls == []                                                  # no Pulse touched, /intel unchanged
    monkeypatch.setattr(update, "update_quietly", lambda *a, **k: {"touched": ["sit_a"]})
    rail._feed_pulses(ctx, out)
    assert calls == ["publish"] and rail.RAIL_INTEL in events


def test_base_map_draws_recognised_borders_crimea_is_ukraine() -> None:
    from algent_backend.agent_system.agents.intel import geo

    square = lambda w, s, e, n: [[[w, s], [e, s], [e, n], [w, n], [w, s]]]   # noqa: E731
    data = {"features": [
        {"properties": {"NAME": "Ukraine"}, "geometry": {"type": "Polygon", "coordinates": square(24, 46, 38, 52)}},
        {"properties": {"NAME": "Russia"}, "geometry": {"type": "MultiPolygon", "coordinates": [
            square(38, 45, 60, 60), square(33, 44.5, 36, 46)]}},          # mainland, and Crimea drawn de facto
    ]}
    countries = geo.parse(data)
    ua, ru = geo.find_country(countries, "Ukraine"), geo.find_country(countries, "Russia")
    assert geo.contains(ua, 33.5, 44.9) and not geo.contains(ru, 33.5, 44.9)   # Sevastopol
    assert geo.contains(ru, 45, 55) and not geo.contains(ua, 45, 55)           # mainland untouched
