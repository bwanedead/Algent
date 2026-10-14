"""Interactive 3D scenes: contract validation, planner routing, record shape, preview, shipped examples."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from algent_backend.agent_system.agents.intel import geo, scene3d, scene_preview, scene_spec as ss
from algent_backend.agent_system.agents.intel import visuals, visuals_facts as vf

SRC = "https://wire.example/ships"
FACT = "Class X submarine: length 115 m and beam 10.3 m, per the navy."


def _sections() -> list[dict]:
    def dev(h, detail):
        return {"headline": h, "detail": detail, "when": "2026-09-29", "significance": "", "statements": [], "sources": [SRC]}
    return [{"theater_id": "thr_a", "name": "Alpha", "headline": "h", "bottom_line": "b", "key_figures": [], "numbers": {},
             "developments": [dev("Spec", FACT), dev("Port", "Berths hit: 12.5% then 31.4%"), dev("More", "Third wave 58.2%"),
                              dev("Fleet", "Fleet of 40 boats")]}]


def _scene(**over) -> dict:
    d = {"title": "A submarine to scale", "caption": "How long the boat is.", "unit": "m", "schematic": True,
         "objects": [{"type": "capsule", "id": "sub", "label": "Class X", "radius": 5.15, "length": 104.7, "cite": "s1"}],
         "sources": [{"id": "s1", "label": "navy", "fact_id": "f1.1", "says": "length 115 m and beam 10.3 m"}]}
    d.update(over)
    return d


def _check(d: dict, **kw) -> list[str]:
    return ss.validate_scene(ss.Scene.model_validate(d), {"f1.1": FACT}, **kw)


def test_traceable_dimension_passes_and_untraceable_is_rejected() -> None:
    assert _check(_scene()) == []
    bad = _scene(objects=[{"type": "capsule", "id": "sub", "radius": 5.15, "length": 160, "cite": "s1"}])
    assert any("length" in p and "not in source" in p for p in _check(bad))
    nocite = _scene(objects=[{"type": "box", "id": "b", "size": [115, 10.3, 5]}])
    assert any("cites no source" in p for p in _check(nocite))


def test_sources_must_be_facts_or_allowed_public_specs() -> None:
    fake = _scene(sources=[{"id": "s1", "label": "navy", "fact_id": "f9.9", "says": "length 115 m"}])
    assert any("not among the day's cited facts" in p for p in _check(fake))
    wrong = _scene(sources=[{"id": "s1", "label": "navy", "fact_id": "f1.1", "says": "length 999 m"}])
    assert any("does not hold" in p for p in _check(wrong))
    pub = _scene(sources=[{"id": "s1", "label": "navy", "url": "https://navy.example/x", "says": "length 115 m, beam 10.3 m"}])
    assert any("allowed public source" in p for p in _check(pub))
    assert _check(pub, allow_public=True) == []


def test_limits_text_numbers_and_timeline() -> None:
    many = _scene(objects=[{"type": "marker", "id": f"m{i}", "real": False} for i in range(5)])
    assert any("limit 3" in p for p in _check(many, max_objects=3))
    assert any("numbers not in any source" in p for p in _check(_scene(caption="It is 777 m long.")))
    tl = {"frames": [{"date": "2026-01-02", "cite": "s1", "pos": {"sub": [0, 0, 0]}}, {"date": "2026-01-01", "cite": "nope", "pos": {"ghost": [0, 0, 0]}}]}
    probs = _check(_scene(timeline=tl))
    assert any("ascending" in p for p in probs) and any("cites no source" in p for p in probs) and any("unknown object" in p for p in probs)
    unsched = _scene(schematic=False, objects=[{"type": "box", "id": "b", "size": [1, 1, 1], "real": False}])
    assert any("not flagged schematic" in p for p in _check(unsched))


def test_coast_is_filled_from_natural_earth_rings() -> None:
    land = geo.Country(name="L", keys={"l"}, polygons=[[[(0.0, 0.0), (2.0, 0.0), (2.0, 2.0), (0.0, 2.0)]]], bbox=(0.0, 0.0, 2.0, 2.0))
    sc = ss.Scene.model_validate({"title": "t", "caption": "c", "unit": "km", "origin": {"lon": 1.0, "lat": 1.0}, "schematic": True,
                                  "objects": [{"type": "coast", "id": "c", "bbox_lonlat": [0.5, 0.5, 1.5, 1.5]}]})
    assert scene3d.fill_coasts(sc, [land]) == []
    ring = sc.objects[0].polygons[0]
    assert len(ring) >= 4 and max(abs(v) for p in ring for v in p) < 100
    assert scene3d.fill_coasts(ss.Scene.model_validate({**sc.model_dump(), "objects": [{"type": "coast", "id": "c", "bbox_lonlat": [9, 9, 10, 10]}]}), [land])


def test_preview_renders_a_png_when_matplotlib_is_reachable() -> None:
    sc = ss.normalize(ss.Scene.model_validate(_scene()))
    try:
        png = scene_preview.render(sc.model_dump(mode="json"))
    except RuntimeError as exc:
        assert "preview render failed" in str(exc)   # no interpreter with matplotlib on this machine
        pytest.skip("no matplotlib reachable")
    assert png[1:4] == b"PNG"


def _ask_scene(d):
    return lambda schema, role, msg: ss.Scene.model_validate(d) if schema is ss.SceneWire else None


def _ask(**kw) -> visuals.VisualAsk:
    base = dict(theater_id="thr_a", form="scene3d", finding="A submarine to scale", caption="How long the boat is.",
                reader_question="How big?", why_not_prose="scale", fact_ids=["f1.1", "f1.2"], spec="one capsule, 115 m")
    return visuals.VisualAsk(**{**base, **kw})


def test_planner_accepts_scene3d_only_grounded_and_enabled(monkeypatch) -> None:
    facts, ids = vf.collect(_sections()), {"thr_a"}
    kept, _ = visuals.validate(visuals.VisualPlan(visuals=[_ask()]), facts, ids, 3)
    assert len(kept) == 1
    kept, dropped = visuals.validate(visuals.VisualPlan(visuals=[_ask(fact_ids=["f1.1"])]), facts, ids, 3)
    assert not kept and "too few" in dropped[0]
    kept, dropped = visuals.validate(visuals.VisualPlan(visuals=[_ask(spec="a 999 m boat")]), facts, ids, 3)
    assert not kept and "numbers not in the cited facts" in dropped[0]
    monkeypatch.setenv("ALGENT_SCENE3D", "0")
    kept, dropped = visuals.validate(visuals.VisualPlan(visuals=[_ask()]), facts, ids, 3)
    assert not kept and "switched off" in dropped[0]


def test_record_shape_and_upload_without_the_harness(monkeypatch) -> None:
    monkeypatch.setattr(scene_preview, "render", lambda scene: b"PNG-fake")
    secs, up = _sections(), []
    def uploader(files):
        up.append(files)
        return {"ok": True, "failed": []}
    rep = visuals.attach(secs, ctx=None, domain="geopolitics", as_of="2026-09-29", ask=lambda s, r, m: (
        visuals.VisualPlan(visuals=[_ask()]) if s is visuals.VisualPlan else ss.Scene.model_validate(_scene())),
        ready=lambda: (False, "no harness"), uploader=uploader)
    assert rep["produced"] == 1, rep
    v = secs[0]["visuals"][0]
    assert v["kind"] == "scene3d" and v["scene"].endswith(".scene.json") and v["preview"].endswith(".png")
    assert v["asset"] == v["preview"] and v["schematic"] is True and v["sources"][0]["url"] == SRC
    assert set(up[0]) == {v["scene"], v["preview"]}
    body = json.loads(up[0][v["scene"]])
    assert body["objects"][0]["type"] == "capsule" and body["alt"]


def test_a_refused_scene_is_a_report_line_not_a_failed_day() -> None:
    secs = _sections()
    bad = _scene(objects=[{"type": "capsule", "id": "sub", "radius": 5.15, "length": 160, "cite": "s1"}])
    rep = visuals.attach(secs, ctx=None, domain="g", as_of="2026-09-29", uploader=lambda f: {"ok": True},
                         ask=lambda s, r, m: visuals.VisualPlan(visuals=[_ask()]) if s is visuals.VisualPlan else ss.Scene.model_validate(bad))
    assert rep["produced"] == 0 and "scene refused" in rep["skipped"][0] and "visuals" not in secs[0]


def test_shipped_example_scenes_satisfy_the_contract() -> None:
    root = Path(__file__).resolve().parents[2] / "sites" / "ohmega-monster" / "public" / "examples"
    for f in sorted(root.glob("scene-*.json")):
        sc = ss.Scene.model_validate_json(f.read_text(encoding="utf-8"))
        assert ss.validate_scene(sc, allow_public=True) == [], f.name
