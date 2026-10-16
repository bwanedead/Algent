"""Native interactive visual forms: timeline and map story specs (grounding, limits), planner routing, hosting,
the SVG stills, and --visuals-only over them (all with fakes, offline)."""

from __future__ import annotations

import json
import xml.etree.ElementTree as ET

import pytest

from algent_backend.agent_system.agents.intel import daily, daily_visuals, flags, native_forms, native_preview, visuals
from algent_backend.agent_system.agents.intel import mapstory_spec as ms
from algent_backend.agent_system.agents.intel import scene_spec as ss
from algent_backend.agent_system.agents.intel import timeline_spec as ts
from algent_backend.agent_system.agents.intel import visuals_facts as vf
from algent_backend.agent_system.agents.intel.visuals_grounding import mentions_date, mentions_place

SRC = "https://wire.example/ukraine"


def _sections() -> list[dict]:
    def dev(h, detail, when):
        return {"headline": h, "detail": detail, "when": when, "significance": "", "statements": [], "sources": [SRC]}
    return [{"theater_id": "thr_a", "name": "Alpha", "headline": "Alpha heats", "bottom_line": "x",
             "developments": [dev("Drone strike", "Drones hit the Kharkiv rail depot, damaging 120 wagons", "2026-10-09"),
                              dev("Talks offered", "Turkey offered to host talks in Istanbul on 11 October", "2026-10-10"),
                              dev("Convoy moves", "A convoy left Belgorod toward Kharkiv", "2026-10-12"),
                              dev("Missile range", "Officials put the missile's range at 500 km from Belgorod", "2026-10-12")],
             "key_figures": [], "numbers": {}}]


def _ask(**kw) -> visuals.VisualAsk:
    base = dict(theater_id="thr_a", form="timeline", finding="Strikes and talks within days",
                caption="Strike, offer, then a convoy.", reader_question="What happened in what order?",
                why_not_prose="sequence", fact_ids=["f1.1", "f1.2", "f1.3", "f1.4"], spec="the four events in order")
    return visuals.VisualAsk(**{**base, **kw})


def _timeline(**over) -> ts.Timeline:
    ev = [ts.Event(id="e1", date="2026-10-09", title="Drones hit Kharkiv rail depot", detail="120 wagons were damaged.",
                   actors=["ua", "ru"], kind="strike", fact_ids=["f1.1"]),
          ts.Event(id="e2", date="2026-10-10", title="Turkey offers to host talks", kind="decision", fact_ids=["f1.2"]),
          ts.Event(id="e3", date="2026-10-12", title="Convoy leaves Belgorod", kind="movement", fact_ids=["f1.3"],
                   place=ts.Place(name="Belgorod", lat=50.6, lon=36.6))]
    return ts.Timeline(**{**dict(title="Strike, offer, convoy", caption="Three days, three moves.", events=ev), **over})


def _facts() -> dict[str, str]:
    return {f.id: f.text for f in vf.collect(_sections())}


# -- grounding helpers -----------------------------------------------------------------

def test_dates_and_places_must_be_stated_by_the_facts() -> None:
    assert mentions_date("talks on 11 October", "2026-10-11") and mentions_date("on October 11th", "2026-10-11")
    assert mentions_date("2026-10-11: x", "2026-10-11") and not mentions_date("talks on 11 October", "2026-10-12")
    assert mentions_place("a convoy left Belgorod", "Belgorod region") and not mentions_place("a convoy left Belgorod", "Gulf of Oman")
    assert not mentions_place("anything", "the North Sea")      # generic words alone name nothing


# -- timeline contract -----------------------------------------------------------------

def test_a_grounded_timeline_passes_and_is_sorted_with_codes_normalised() -> None:
    tl = _timeline()
    tl.events.reverse()
    assert ts.ground(tl, _facts()) == []
    assert [e.id for e in tl.events] == ["e1", "e2", "e3"] and tl.events[0].actors == ["UA", "RU"]
    assert ts.alt_text(tl).startswith("Strike, offer, convoy. Three days, three moves. 2026-10-09: Drones hit")


def test_ungrounded_events_are_dropped_and_too_few_refuses() -> None:
    tl = _timeline()
    tl.events[0].detail = "27 wagons were damaged."                  # a number the facts lack
    tl.events[1].date = "2026-10-20"                               # a date no cited fact states
    tl.events[2].title = " ".join(["word"] * 11)                    # over the title limit
    notes = ts.ground(tl, _facts())
    assert len(tl.events) == 0 and len(ts.refused(notes)) == 1 and len([n for n in notes if "dropped" in n]) == 3


def test_foreign_place_lane_and_title_numbers() -> None:
    tl = _timeline()
    tl.events[2].place = ts.Place(name="Gulf of Oman", lat=25.0, lon=57.0)
    tl.lanes = [ts.Lane(id="a", label="Ukraine"), ts.Lane(id="b", label="Russia")]
    tl.events[0].lane, tl.events[1].lane = "a", "b"
    notes = ts.ground(tl, _facts())
    assert tl.events[2].place is None and any("place" in n for n in notes) and len(tl.lanes) == 2
    tl.title = "Strikes up 300 percent"
    assert ts.refused(ts.ground(tl, _facts()))
    one = _timeline()                                              # lanes that never separate threads are removed
    one.lanes = [ts.Lane(id="a", label="Ukraine")]
    one.events[0].lane = "a"
    ts.ground(one, _facts())
    assert one.lanes == [] and one.events[0].lane == ""


# -- map story contract ----------------------------------------------------------------

def _story() -> ms.MapStory:
    kh = ms.Point(id="kh", label="Rail depot hit", place="Kharkiv", tone="hot", at=ms.Pt(lat=49.99, lon=36.23))
    cv = ms.Route(id="cv", label="Convoy", places=["Belgorod", "Kharkiv"], path=[ms.Pt(lat=50.6, lon=36.6), ms.Pt(lat=49.99, lon=36.23)])
    rg = ms.Range(id="rg", label="Missile reach", place="Belgorod", at=ms.Pt(lat=50.6, lon=36.6), radius_km=500)
    return ms.MapStory(title="Strike, then a convoy", caption="What moved around Kharkiv.", steps=[
        ms.Step(date="2026-10-09", caption="Drones hit the rail depot.", fact_ids=["f1.1"], show=[kh]),
        ms.Step(date="2026-10-12", caption="A convoy leaves Belgorod.", fact_ids=["f1.3", "f1.4"], show=[cv, rg], hide=["kh", "nope"])])


def test_a_grounded_map_story_passes_and_is_framed() -> None:
    st = _story()
    assert ms.ground(st, _facts()) == []
    assert len(st.bounds) == 4 and st.bounds[0] < 36.23 < st.bounds[2] and st.bounds[1] < 49.99 < st.bounds[3]
    assert st.steps[1].hide == ["kh"]                              # a hide of an id never shown is noise
    assert ms.alt_text(st).startswith("Strike, then a convoy.")


def test_map_story_features_must_stand_on_the_facts() -> None:
    st = _story()
    st.steps[1].show[1].radius_km = 900                            # a range no fact states
    st.steps[0].show[0].place = "Gulf of Oman"                     # a place no fact speaks of
    notes = ms.ground(st, _facts())
    assert sum("dropped" in n for n in notes) == 2 and [f.id for f in st.steps[1].show] == ["cv"]
    bad = _story()
    bad.steps[1].date = "2026-10-30"
    assert any(n.startswith("REFUSED") for n in ms.ground(bad, _facts()))


# -- planner routing and hosting -------------------------------------------------------

def _attach(plan, specs, *, uploads=None, **kw):
    uploads = uploads if uploads is not None else []
    asked: list[str] = []

    def ask(schema, role, task):
        asked.append(schema.__name__.removesuffix("Wire"))
        return plan if schema is visuals.VisualPlan else specs[schema.__name__.removesuffix("Wire")]

    def not_the_harness(*_a, **_k):
        raise AssertionError("native forms must never reach the coding harness")

    secs = _sections()
    rep = visuals.attach(secs, ctx=None, domain="geopolitics", as_of="2026-10-14", ask=ask, ready=not_the_harness,
                         runner=not_the_harness, uploader=lambda files: uploads.append(files) or {"ok": True, "failed": []}, **kw)
    return secs, rep, asked, uploads


def test_a_timeline_ask_is_built_natively_and_never_drawn_by_the_harness() -> None:
    secs, rep, asked, uploads = _attach(visuals.VisualPlan(visuals=[_ask()]), {"Timeline": _timeline()})
    assert rep["produced"] == 1 and asked == ["VisualPlan", "Timeline"], rep
    v = secs[0]["visuals"][0]
    assert v["kind"] == "timeline" and v["spec"].endswith(".timeline.json") and v["asset"].endswith(".timeline.svg")
    assert v["sources"] == [{"label": "wire.example", "url": SRC}] and v["generator"] == "native"
    files = uploads[0]
    spec = json.loads(files[v["spec"]])
    assert spec["now"] == "2026-10-14" and spec["events"][0]["sources"][0]["url"] == SRC and spec["alt"]
    ET.fromstring(files[v["preview"]].decode("utf-8"))             # the still is well-formed SVG


def test_a_map_story_ask_is_built_natively_with_a_still() -> None:
    secs, rep, asked, uploads = _attach(visuals.VisualPlan(visuals=[_ask(form="mapstory")]), {"MapStory": _story()})
    assert rep["produced"] == 1 and asked == ["VisualPlan", "MapStory"], rep
    v = secs[0]["visuals"][0]
    assert v["kind"] == "mapstory" and v["spec"].endswith(".mapstory.json")
    root = ET.fromstring(uploads[0][v["preview"]].decode("utf-8"))
    assert root.tag.endswith("svg")


def test_refused_native_spec_is_a_report_line_not_a_failed_day() -> None:
    tl = _timeline()
    tl.events = tl.events[:2]
    secs, rep, _, uploads = _attach(visuals.VisualPlan(visuals=[_ask()]), {"Timeline": tl})
    assert rep["produced"] == 0 and "refused" in rep["skipped"][0] and "visuals" not in secs[0] and not uploads


def test_native_forms_can_be_switched_off(monkeypatch) -> None:
    monkeypatch.setenv("ALGENT_NATIVE_FORMS", "0")
    assert not flags.native_forms_enabled()
    kept, dropped = visuals.validate(visuals.VisualPlan(visuals=[_ask(), _ask(form="mapstory")]),
                                     vf.collect(_sections()), {"thr_a"}, 3)
    assert not kept and "switched off" in dropped[0]


def test_native_forms_ignore_a_source_hint_and_chart_forms_still_need_numbers() -> None:
    kept, _ = visuals.validate(visuals.VisualPlan(visuals=[_ask(fact_ids=["f1.1"], source_hint="CSIS")]),
                               vf.collect(_sections()), {"thr_a"}, 3)
    assert not kept                                                # one fact is too few without a real public spec
    plan = visuals.VisualPlan(visuals=[_ask(form="mapstory", caption="A 900 km sweep.")])
    kept, dropped = visuals.validate(plan, vf.collect(_sections()), {"thr_a"}, 3)
    assert not kept and "numbers not in the cited facts" in dropped[0]


def test_planner_doctrine_names_the_native_forms() -> None:
    for word in ("mapstory", "timeline", "scene3d", "QUALITY GATE", "RULED OUT"):
        assert word in visuals.PLAN_ROLE


# -- stills ----------------------------------------------------------------------------

def test_stills_are_valid_svg_even_for_a_bare_story() -> None:
    tl = _timeline()
    ts.ground(tl, _facts())
    ET.fromstring(native_preview.timeline_svg(tl))
    bare = ms.MapStory(title="t", caption="c", steps=[])
    ET.fromstring(native_preview.mapstory_svg(bare))


# -- visuals-only ----------------------------------------------------------------------

def test_visuals_only_regenerates_today_as_a_native_timeline(tmp_path, monkeypatch) -> None:
    monkeypatch.setattr(daily, "daily_dir", lambda _d: tmp_path)
    record = {"schema": 1, "domain": "geopolitics", "date": "2026-10-14", "summary": {"headline": "H", "the_day": []},
              "theaters": _sections()}
    record["theaters"][0]["visuals"] = [{"id": "old", "kind": "timeline", "asset": "/analytics/daily/old.svg"}]
    (tmp_path / "2026-10-14.json").write_text(json.dumps(record), encoding="utf-8")
    asked: list[str] = []
    uploads: list[dict] = []

    def ask(schema, role, task):
        asked.append(schema.__name__.removesuffix("Wire"))
        return visuals.VisualPlan(visuals=[_ask()]) if schema is visuals.VisualPlan else _timeline()

    def no_harness(*_a, **_k):
        raise AssertionError("harness used")

    out = daily_visuals.redo(None, None, "geopolitics", "2026-10-14", fresh=True, ask=ask, ready=no_harness, runner=no_harness,
                             uploader=lambda files: uploads.append(files) or {"ok": True, "failed": []})
    assert out["produced"] == 1 and asked == ["VisualPlan", "Timeline"], out
    saved = json.loads((tmp_path / "2026-10-14.json").read_text(encoding="utf-8"))
    v = saved["theaters"][0]["visuals"]
    assert len(v) == 1 and v[0]["kind"] == "timeline" and v[0]["spec"] and saved["summary"] == {"headline": "H", "the_day": []}
    assert native_forms.NATIVE_FORMS == ("timeline", "mapstory")


@pytest.mark.parametrize("bad", ["2026-13-01", "2026-10-1", "tomorrow", ""])
def test_malformed_dates_are_not_dates(bad: str) -> None:
    assert not ts.valid_date(bad)


# -- the wire schemas the model fills carry no unions (the house provider rejects oneOf/anyOf) ----------

def _has_union(node) -> bool:
    if isinstance(node, dict):
        return any(k in ("oneOf", "anyOf", "allOf") or _has_union(v) for k, v in node.items())
    return isinstance(node, list) and any(_has_union(v) for v in node)


@pytest.mark.parametrize("schema", [ms.MapStoryWire, ts.TimelineWire, ss.SceneWire])
def test_wire_schemas_have_no_oneof_or_anyof(schema) -> None:
    assert not _has_union(schema.model_json_schema())


def test_a_flat_map_story_wire_builds_the_strict_spec_and_drops_the_malformed() -> None:
    pt = ms.Pt(lat=49.99, lon=36.23)
    wire = ms.MapStoryWire(title="t", caption="c", steps=[ms.StepWire(date="2026-10-09", caption="x", fact_ids=["f1.1"], show=[
        ms.FeatureWire(id="a", kind="point", place="Kharkiv", at=[pt]),
        ms.FeatureWire(id="b", kind="route", places=["Belgorod", "Kharkiv"], path=[pt, pt]),
        ms.FeatureWire(id="c", kind="range", place="Belgorod", at=[pt], radius_km=500),
        ms.FeatureWire(id="bad", kind="point", place="Kharkiv")])])           # a point with no position
    spec, notes = ms.from_wire(wire)
    assert [f.type for f in spec.steps[0].show] == ["point", "route", "range"] and len(notes) == 1 and "'bad'" in notes[0]


def test_a_flat_timeline_wire_builds_places_only_when_located() -> None:
    w = ts.TimelineWire(title="t", caption="c", events=[
        ts.EventWire(id="e1", date="2026-10-09", title="x", place_name="Kharkiv", place_located=True, place_lat=49.9, place_lon=36.2),
        ts.EventWire(id="e2", date="2026-10-10", title="y", place_name="Belgorod", place_lat=0, place_lon=0)])
    spec, notes = ts.from_wire(w)
    assert spec.events[0].place.lat == 49.9 and spec.events[1].place.lat is None and not notes


def test_a_flat_scene_wire_builds_the_strict_scene() -> None:
    w = ss.SceneWire(title="t", caption="c", has_origin=True, origin_lon=1.0, origin_lat=2.0, objects=[
        ss.ObjWire(id="b", type="box", size=[1, 1, 1]), ss.ObjWire(id="s", type="sphere", radius=2),
        ss.ObjWire(id="bad", type="cylinder")])                                # no radius/height
    scene, notes = ss.from_wire(w)
    assert [o.type for o in scene.objects] == ["box", "sphere"] and scene.origin.lat == 2.0 and len(notes) == 1


def test_a_wire_answer_from_the_model_is_converted_in_produce() -> None:
    wire = ms.MapStoryWire(title="Strike, then a convoy", caption="What moved around Kharkiv.", steps=[
        ms.StepWire(date="2026-10-09", caption="Drones hit the rail depot.", fact_ids=["f1.1"],
                    show=[ms.FeatureWire(id="kh", kind="point", label="Rail depot hit", place="Kharkiv", at=[ms.Pt(lat=49.99, lon=36.23)])]),
        ms.StepWire(date="2026-10-12", caption="A convoy leaves Belgorod.", fact_ids=["f1.3"],
                    show=[ms.FeatureWire(id="cv", kind="route", places=["Belgorod", "Kharkiv"],
                                         path=[ms.Pt(lat=50.6, lon=36.6), ms.Pt(lat=49.99, lon=36.23)])])])
    secs, rep, asked, _ = _attach(visuals.VisualPlan(visuals=[_ask(form="mapstory")]), {"MapStory": wire})
    assert rep["produced"] == 1 and secs[0]["visuals"][0]["kind"] == "mapstory", rep
