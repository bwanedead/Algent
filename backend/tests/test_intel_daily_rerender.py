"""The draft archive and the model-free rerender: environment faults never force a paid rewrite."""

from __future__ import annotations

import json

import pytest

from algent_backend.agent_system.agents.intel import daily, daily_drafts, daily_rerender, geo
from algent_backend.agent_system.agents.intel.contracts import Development, Place
from algent_backend.publishing import intel_page

from test_intel_daily import AS_OF, SRC_A, SUMMARY, _board, _ctx, _draft, _store

PORT = Place(name="Port", country="Aland", lat=10.0, lon=10.0)


def _basemap() -> list[geo.Country]:
    ring = [[[0, 0], [20, 0], [20, 20], [0, 20], [0, 0]]]
    return geo.parse({"type": "FeatureCollection", "features": [{
        "type": "Feature", "properties": {"NAME": "Aland", "ADMIN": "Aland", "ISO_A3": "ALA", "ISO_A2": "AL"},
        "geometry": {"type": "Polygon", "coordinates": ring}}]})


def _dev(**kw) -> Development:
    return Development(headline="Strike on port", when="2026-09-28", sources=[SRC_A], place=PORT, **kw)


@pytest.fixture
def day(tmp_path, monkeypatch):
    """A day produced on a machine with NO basemap: every place was dropped from the published record."""
    _store(tmp_path, monkeypatch)
    monkeypatch.setattr(geo, "load", lambda *_a, **_k: None)
    ctx = _ctx({"Alpha": _draft(developments=[_dev()]), "Bravo": _draft(developments=[_dev()])}, SUMMARY)
    res = daily.produce_daily(ctx, domain="geopolitics", top=5, research=False, model_spec=None, as_of=AS_OF,
                              board=_board())
    return tmp_path, res["report"]


def _no_model(monkeypatch) -> None:
    def boom(*_a, **_k):
        raise AssertionError("a rerender must never call a model")
    monkeypatch.setattr(daily, "_ask", boom)


def test_archive_keeps_raw_drafts_and_is_not_published(day) -> None:
    tmp_path, record = day
    assert all(s["developments"][0]["place"] is None and s["map"] is None for s in record["theaters"])   # dropped
    arc = daily_drafts.load("geopolitics", AS_OF)
    assert set(arc["theaters"]) == {"thr_a", "thr_b"} and "summary" in arc
    raw = arc["theaters"]["thr_a"]["draft"]["developments"][0]["place"]
    assert raw["name"] == "Port"                                            # the model's value survives the guard
    assert "research_urls" in arc["theaters"]["thr_a"]["inputs"]
    daily_dir = tmp_path / "intel" / "daily" / "geopolitics"
    assert [p.name for p in daily_dir.iterdir()] == [f"{AS_OF}.json"]       # nothing but the record is mirrored
    assert [r["date"] for r in intel_page._daily_reports(tmp_path / "intel")] == [AS_OF]
    assert "daily_drafts" not in json.dumps(record)


def test_rerender_restores_places_with_zero_model_calls(day, monkeypatch) -> None:
    tmp_path, before = day
    _no_model(monkeypatch)
    res = daily_rerender.rerender("geopolitics", AS_OF, countries=_basemap())
    assert res["redone"] == ["thr_a", "thr_b"] and res["warnings"] == []
    for sec in res["report"]["theaters"]:
        assert sec["developments"][0]["place"]["country"] == "Aland" and sec["map"] is not None
    saved = json.loads((tmp_path / "intel" / "daily" / "geopolitics" / f"{AS_OF}.json").read_text(encoding="utf-8"))
    assert saved == res["report"]
    assert saved["summary"] == before["summary"] and saved["cross_theater"] == before["cross_theater"]
    assert saved["theaters"][0]["bottom_line"] == before["theaters"][0]["bottom_line"]


def test_rerender_without_basemap_warns_and_keeps_drafts(day, monkeypatch) -> None:
    _no_model(monkeypatch)
    monkeypatch.setattr(geo, "load", lambda *_a, **_k: None)
    res = daily_rerender.rerender("geopolitics", AS_OF)
    assert res["warnings"] and res["report"]["theaters"][0]["map"] is None
    assert daily_drafts.load("geopolitics", AS_OF)["theaters"]["thr_a"]["draft"]["developments"][0]["place"]


def test_rerender_theater_filter_touches_only_those(day, monkeypatch) -> None:
    _no_model(monkeypatch)
    res = daily_rerender.rerender("geopolitics", AS_OF, only=["thr_a"], countries=_basemap())
    a, b = res["report"]["theaters"]
    assert res["redone"] == ["thr_a"]
    assert a["developments"][0]["place"] is not None and b["developments"][0]["place"] is None


def test_rerender_needs_an_archive(day, monkeypatch) -> None:
    daily_drafts.path_for("geopolitics", AS_OF).unlink()
    assert "no draft archive" in daily_rerender.rerender("geopolitics", AS_OF, countries=_basemap())["error"]


def test_tag_places_changes_no_text_and_adds_only_valid_places(day, monkeypatch) -> None:
    daily_drafts.path_for("geopolitics", AS_OF).unlink()                    # a report from before the archive
    before = json.loads(json.dumps(day[1]))
    calls: list[str] = []

    class Model:
        def with_structured_output(self, schema):
            calls.append(schema.__name__)
            return self

        def invoke(self, messages, **_k):
            assert "Strike on port" in messages[1].content
            return daily_rerender.PlaceTags(tags=[
                daily_rerender.PlaceTag(ref="T0.0", place=PORT),
                daily_rerender.PlaceTag(ref="T1.0", place=Place(name="Nowhere", country="Aland", lat=60, lon=60)),
                daily_rerender.PlaceTag(ref="T9.9", place=PORT)])

    ctx = type("X", (), {"model_resolver": type("R", (), {
        "resolve": lambda _s, _spec: type("C", (), {"client": Model()})()})()})()
    res = daily_rerender.tag_places(ctx, None, "geopolitics", AS_OF, countries=_basemap())
    assert calls == ["PlaceTags"] and (res["asked"], res["tagged"]) == (2, 1)       # one call for the whole report
    after = res["report"]
    assert after["theaters"][0]["developments"][0]["place"]["name"] == "Port" and after["theaters"][0]["map"]
    assert after["theaters"][1]["developments"][0]["place"] is None             # off the map: refused
    for rec in (before, after):                                                  # everything else is identical
        for sec in rec["theaters"]:
            sec["map"] = None
            sec["developments"][0]["place"] = None
    assert before == after
