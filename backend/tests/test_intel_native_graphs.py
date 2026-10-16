"""The network, flow and tracker-comparison native forms: grounding (a tie or route must be stated by cited facts,
tracker ids must be in the catalog and cleared for public display), flat wire schemas, planner routing, hosting,
the SVG stills and --visuals-only (all with fakes, offline)."""

from __future__ import annotations

import json
import xml.etree.ElementTree as ET
from datetime import date, timedelta

import pytest

from algent_backend.agent_system.agents.intel import daily, daily_visuals, flow_spec as fs, native_forms, native_preview_graphs as graphs
from algent_backend.agent_system.agents.intel import network_spec as ns, tracker_compare_spec as tc, visuals
from algent_backend.agent_system.agents.intel import visuals_facts as vf
from algent_backend.agent_system.agents.intel.visuals_grounding import mentions_entity
from algent_backend.instruments import store as istore
from algent_backend.instruments.contracts import Observation

SRC = "https://wire.example/gulf"
AS_OF = "2026-10-14"


def _sections() -> list[dict]:
    def dev(h, detail, when):
        return {"headline": h, "detail": detail, "when": when, "significance": "", "statements": [], "sources": [SRC]}
    return [{"theater_id": "thr_a", "name": "Gulf", "headline": "Gulf heats", "bottom_line": "x",
             "developments": [dev("Iran arms Houthis", "Iran shipped anti-ship missiles to the Houthis, a UN panel reported", "2026-10-03"),
                              dev("Red Sea attacks", "The Houthis attacked tankers in the Red Sea", "2026-10-08"),
                              dev("US sanctions", "The US sanctioned Iranian shipping firms", "2026-10-09"),
                              dev("Gulf oil", "About 2.1 million barrels a day of crude flows from the Gulf through Hormuz to Asia", "2026-10-01"),
                              dev("Hormuz closed", "On 10 October Iran closed the Strait of Hormuz and a Saudi pipeline to Yanbu that can carry 4.5 million barrels a day took some crude for Asian buyers", "2026-10-10")],
             "key_figures": [], "numbers": {}}]


def _facts() -> dict[str, str]:
    return {f.id: f.text for f in vf.collect(_sections())}


def _ask(**kw) -> visuals.VisualAsk:
    base = dict(theater_id="thr_a", form="network", finding="Iran arms the Houthis", caption="Who backs whom around the Red Sea.",
                reader_question="Who is behind the attacks?", why_not_prose="web of ties", fact_ids=["f1.1", "f1.2", "f1.3", "f1.4", "f1.5"],
                spec="the ties between Iran, the Houthis and the US")
    return visuals.VisualAsk(**{**base, **kw})


# -- network ---------------------------------------------------------------------------

def _network() -> ns.Network:
    nodes = [ns.Node(id="ir", label="Iran", kind="state", iso="ir"), ns.Node(id="hu", label="Houthis", kind="group"),
             ns.Node(id="us", label="US", kind="state", iso="US"), ns.Node(id="ye", label="Red Sea shipping", kind="place")]
    edges = [ns.Edge(id="e1", source="ir", target="hu", relation="arms", strength=3, detail="Missiles shipped, a UN panel said.", start="2026-10-03", fact_ids=["f1.1"]),
             ns.Edge(id="e2", source="hu", target="ye", relation="attacks", fact_ids=["f1.2"]),
             ns.Edge(id="e3", source="us", target="ir", relation="sanctions", fact_ids=["f1.3"]),
             ns.Edge(id="e4", source="us", target="hu", relation="opposes", fact_ids=["f1.3"])]       # the facts never name the Houthis here
    return ns.Network(title="Iran arms the Houthis", caption="Ties around the Red Sea.", nodes=nodes, edges=edges)


def test_entities_are_named_by_a_word_or_an_acronym() -> None:
    assert mentions_entity("The US sanctioned firms", "United States (US)") and mentions_entity("Iran arms", "Iran")
    assert not mentions_entity("The Houthis attacked", "US") and not mentions_entity("Iran", "Saudi Arabia")


def test_a_grounded_network_keeps_stated_ties_and_drops_the_rest() -> None:
    net = _network()
    notes = ns.ground(net, _facts())
    assert [e.id for e in net.edges] == ["e1", "e2", "e3"] and any("e4" in n and "'Houthis' is not named" in n for n in notes)
    assert {n.id for n in net.nodes} == {"ir", "hu", "us", "ye"} and net.nodes[0].iso == "IR"
    assert ns.frame_dates(net) == ["2026-10-03"] and "Iran arms the Houthis" in ns.alt_text(net)
    assert not ts_refused(notes)


def ts_refused(notes: list[str]) -> list[str]:
    return [n for n in notes if n.startswith("REFUSED")]


def test_network_dates_figures_and_sizes_must_be_stated() -> None:
    net = _network()
    net.edges[0].start = "2026-10-05"                                 # no cited fact states it
    net.edges[1].detail = "Hit 70 tankers."                            # a number the fact lacks
    net.nodes[0].weight, net.weight_label = 61.0, "defence budget"    # no fact holds it
    notes = ns.ground(net, _facts())
    assert [e.id for e in net.edges] == ["e3"] and ts_refused(notes) and any("size cleared" in n for n in notes)
    assert net.weight_label == ""


def test_a_network_with_a_sized_node_keeps_a_figure_its_facts_hold() -> None:
    net = _network()
    net.nodes[0].weight, net.nodes[0].fact_ids, net.weight_label = 2.1, ["f1.4"], "oil flowing past, million barrels a day"
    ns.ground(net, _facts())
    assert net.nodes[0].weight == 2.1 and net.weight_label


def test_a_relation_that_ends_before_it_starts_is_dropped_and_numbers_in_the_title_refuse() -> None:
    net = _network()
    net.edges[0].end, net.edges[0].fact_ids = "2026-10-01", ["f1.1", "f1.4"]      # both dates are stated, in the wrong order
    net.title = "Strikes up 300 percent"
    notes = ns.ground(net, _facts())
    assert any("ends before" in n for n in notes) and ts_refused(notes)


# -- flow ------------------------------------------------------------------------------

def _flowmap() -> fs.FlowMap:
    places = [fs.Place(id="gulf", name="Gulf", role="source", lat=27.0, lon=51.0), fs.Place(id="hormuz", name="Strait of Hormuz", role="chokepoint", lat=26.57, lon=56.25),
              fs.Place(id="asia", name="Asia", role="sink", lat=30.0, lon=100.0), fs.Place(id="yanbu", name="Yanbu", role="hub", lat=24.1, lon=38.1),
              fs.Place(id="nowhere", name="Atlantis", lat=0.0, lon=-30.0)]
    flows = [fs.Flow(id="f1", source="gulf", target="asia", via=["hormuz"], commodity="crude oil", amount=2.1, unit="million barrels a day", detail="Through Hormuz.", fact_ids=["f1.4"]),
             fs.Flow(id="f2", source="yanbu", target="asia", commodity="crude oil", amount=70, unit="million barrels a day", fact_ids=["f1.5"]),     # 70 is no cited figure
             fs.Flow(id="f3", source="gulf", target="asia", commodity="gas", fact_ids=["f1.4"])]                                                    # facts never say gas, but ends are named
    dis = [fs.Disruption(id="d1", date="2026-10-10", breaks=["f1"], reroutes=["f2"], effect="Iran closed Hormuz; some crude took the Yanbu pipeline.", fact_ids=["f1.5"])]
    return fs.FlowMap(title="Hormuz closes, crude reroutes", caption="Oil from the Gulf to Asia.", places=places, flows=flows, disruptions=dis)


def test_a_grounded_flow_map_clears_unstated_amounts_and_frames_the_places() -> None:
    spec = _flowmap()
    notes = fs.ground(spec, _facts())
    by = {f.id: f for f in spec.flows}
    assert by["f1"].amount == 2.1 and by["f2"].amount == 0 and by["f2"].unit == "" and any("amount cleared" in n for n in notes)
    assert "nowhere" not in {p.id for p in spec.places} and len(spec.bounds) == 4 and spec.bounds[0] < 38.1 < 56.25 < spec.bounds[2]
    assert [d.id for d in spec.disruptions] == ["d1"] and spec.disruptions[0].reroutes == ["f2"] and not ts_refused(notes)
    assert "Crude oil flows from Gulf to Asia" in fs.alt_text(spec)


def test_flows_and_disruptions_must_name_their_ends_and_date() -> None:
    spec = _flowmap()
    spec.flows[0].source = "yanbu"                                    # f1's facts never name Yanbu
    spec.disruptions[0].date = "2026-10-12"                           # not stated by its fact
    notes = fs.ground(spec, _facts())
    assert "f1" not in {f.id for f in spec.flows} and spec.disruptions == [] and any("disruption" in n for n in notes)


def test_a_flow_map_with_too_few_flows_is_refused() -> None:
    spec = _flowmap()
    spec.flows = spec.flows[:1]
    assert ts_refused(fs.ground(spec, _facts()))


def test_off_globe_places_are_dropped() -> None:
    spec = _flowmap()
    spec.places[0].lat = 127.0
    notes = fs.ground(spec, _facts())
    assert any("off the globe" in n for n in notes) and "gulf" not in {p.id for p in spec.places}


def test_flow_widths_are_in_proportion_to_stated_amounts_of_one_unit() -> None:
    spec = _flowmap()
    spec.flows[1].amount, spec.flows[1].unit = 1.0, "million barrels a day"
    w = graphs.width_of(spec)
    assert w["f1"] > w["f2"] > 1.5 and w["f3"] == 2.5


# -- tracker comparison ----------------------------------------------------------------

@pytest.fixture()
def store(tmp_path, monkeypatch):
    monkeypatch.setenv("ALGENT_INSTRUMENTS_STORE", str(tmp_path / "istore"))
    end = date.fromisoformat(AS_OF)

    def put(series_id: str, base: float, n: int = 60, slope: float = 0.0) -> None:
        istore.append(series_id, [Observation(series_id=series_id, period=(end - timedelta(days=n - 1 - i)).isoformat(), value=base + slope * i,
                                              fetched_at="2026-10-14T00:00:00+00:00", source_url="https://portwatch.imf.org/") for i in range(n)])

    put("chk_hormuz_transits", 100.0, slope=-0.5)
    put("chk_hormuz_tanker_transits", 40.0, slope=-0.2)
    put("px_brent", 80.0, slope=0.3)                                   # an unofficial market feed: internal-only
    put("chk_suez_transits", 50.0, n=3)                                # too few points
    return tmp_path


def _compare(*ids: str, **kw) -> tc.TrackerCompare:
    wire = tc.TrackerCompareWire(title="Transits fell as tankers thinned", caption="Hormuz traffic since the closure.", window_days=45,
                                 series=[tc.PickWire(id=i, label="Ships") for i in ids],
                                 markers=[tc.MarkerWire(date="2026-10-10", label="Iran closes Hormuz", fact_ids=["f1.5"]),
                                          tc.MarkerWire(date="2026-10-11", label="Unstated day", fact_ids=["f1.5"])])
    spec, _ = tc.from_wire(wire)
    return spec.model_copy(update=kw) if kw else spec


def test_only_catalog_public_series_with_stored_points_are_offered(store) -> None:
    ids = {r["id"] for r in tc.available(AS_OF)}
    assert ids == {"chk_hormuz_transits", "chk_hormuz_tanker_transits"}                 # not px_brent (internal), not suez (3 points)
    assert "chk_hormuz_transits" in tc.available_block(AS_OF) and "px_brent" not in tc.available_block(AS_OF)


def test_series_are_read_from_the_store_and_the_model_writes_no_data_point(store) -> None:
    spec = _compare("chk_hormuz_transits", "chk_hormuz_tanker_transits", "px_brent", "chk_suez_transits", "made_up_series")
    notes = tc.ground(spec, _facts(), AS_OF)
    assert [ln.id for ln in spec.series] == ["chk_hormuz_transits", "chk_hormuz_tanker_transits"] and not ts_refused(notes)
    first = spec.series[0]
    assert spec.window_days == 60 and first.unit == "ships/day" and first.source == "IMF PortWatch" and first.source_url.startswith("http")
    assert first.dates[-1] == AS_OF and first.values[-1] == pytest.approx(100.0 - 0.5 * 59, abs=1e-3)
    assert any("internal-only" in n for n in notes)
    assert any("not a series of the catalog" in n for n in notes) and any("fewer than" in n for n in notes)
    assert [m.date for m in spec.markers] == ["2026-10-10"] and any("2026-10-11" in n for n in notes)
    assert "Ships:" in tc.alt_text(spec)


def test_fewer_than_two_usable_series_refuses(store) -> None:
    spec = _compare("chk_hormuz_transits", "px_brent")
    assert ts_refused(tc.ground(spec, _facts(), AS_OF))


def test_numbers_in_the_title_must_come_from_the_facts(store) -> None:
    spec = _compare("chk_hormuz_transits", "chk_hormuz_tanker_transits", title="Transits down 80 percent")
    assert ts_refused(tc.ground(spec, _facts(), AS_OF))


# -- wire schemas ----------------------------------------------------------------------

def _has_union(node) -> bool:
    if isinstance(node, dict):
        return any(k in ("oneOf", "anyOf", "allOf") or _has_union(v) for k, v in node.items())
    return isinstance(node, list) and any(_has_union(v) for v in node)


@pytest.mark.parametrize("schema", [ns.NetworkWire, fs.FlowWire, tc.TrackerCompareWire, visuals.VisualPlan])
def test_wire_schemas_have_no_oneof_or_anyof(schema) -> None:
    assert not _has_union(schema.model_json_schema())


# -- planner routing and hosting -------------------------------------------------------

def _attach(plan, specs, *, uploads=None):
    uploads = uploads if uploads is not None else []
    asked: list[tuple[str, str]] = []

    def ask(schema, role, task):
        asked.append((schema.__name__.removesuffix("Wire"), task))
        return plan if schema is visuals.VisualPlan else specs[schema.__name__.removesuffix("Wire")]

    def not_the_harness(*_a, **_k):
        raise AssertionError("native forms must never reach the coding harness")

    secs = _sections()
    rep = visuals.attach(secs, ctx=None, domain="geopolitics", as_of=AS_OF, ask=ask, ready=not_the_harness, runner=not_the_harness,
                         uploader=lambda files: uploads.append(files) or {"ok": True, "failed": []})
    return secs, rep, asked, uploads


def test_the_planner_may_choose_the_new_native_forms_and_doctrine_names_them() -> None:
    for word in ("network", "flow", "tracker_compare", "QUALITY GATE", "TRACKERS COMPARED"):
        assert word in visuals.PLAN_ROLE
    assert {"network", "flow", "tracker_compare"} <= visuals._NATIVE and "flow" not in visuals._SIGNPOSTED
    assert native_forms.NATIVE_FORMS == ("timeline", "mapstory", "network", "flow", "tracker_compare")


def test_a_network_ask_is_built_natively_with_a_still() -> None:
    secs, rep, asked, uploads = _attach(visuals.VisualPlan(visuals=[_ask()]), {"Network": _network()})
    assert rep["produced"] == 1 and [a[0] for a in asked] == ["VisualPlan", "Network"], rep
    v = secs[0]["visuals"][0]
    assert v["kind"] == "network" and v["spec"].endswith(".network.json") and v["asset"].endswith(".network.svg") and v["generator"] == "native"
    spec = json.loads(uploads[0][v["spec"]])
    assert len(spec["edges"]) == 3 and spec["edges"][0]["sources"][0]["url"] == SRC and spec["alt"]
    assert v["sources"] == [{"label": "wire.example", "url": SRC}]
    ET.fromstring(uploads[0][v["preview"]].decode("utf-8"))
    assert any("e4" in t for t in rep.get("trimmed", []))


def test_a_flow_ask_is_built_natively_and_the_still_is_svg() -> None:
    secs, rep, asked, uploads = _attach(visuals.VisualPlan(visuals=[_ask(form="flow", finding="Hormuz closes", caption="Crude reroutes.")]), {"FlowMap": _flowmap()})
    assert rep["produced"] == 1, rep
    v = secs[0]["visuals"][0]
    assert v["kind"] == "flow" and v["spec"].endswith(".flow.json") and not v["schematic"]
    spec = json.loads(uploads[0][v["spec"]])
    assert spec["bounds"] and spec["disruptions"][0]["sources"] and spec["flows"][0]["amount"] == 2.1
    ET.fromstring(uploads[0][v["preview"]].decode("utf-8"))


def test_a_tracker_compare_ask_gets_the_series_list_and_hosts_instrument_sources(store) -> None:
    wire = tc.TrackerCompareWire(title="Transits fell as tankers thinned", caption="Hormuz traffic since the closure.", window_days=60,
                                 series=[tc.PickWire(id="chk_hormuz_transits", label="All ships"), tc.PickWire(id="chk_hormuz_tanker_transits", label="Tankers")],
                                 markers=[tc.MarkerWire(date="2026-10-10", label="Iran closes Hormuz", fact_ids=["f1.5"])])
    secs, rep, asked, uploads = _attach(visuals.VisualPlan(visuals=[_ask(form="tracker_compare", finding="Hormuz traffic thins",
                                                                          spec="Hormuz transits against tanker counts")]), {"TrackerCompare": wire})
    assert rep["produced"] == 1, rep
    assert "SERIES YOU MAY COMPARE" in asked[1][1] and "chk_hormuz_transits" in asked[1][1]
    v = secs[0]["visuals"][0]
    assert v["kind"] == "tracker_compare" and {"label": "IMF PortWatch", "url": "https://portwatch.imf.org/"} in v["sources"]
    spec = json.loads(uploads[0][v["spec"]])
    assert len(spec["series"]) == 2 and spec["series"][0]["dates"][-1] == AS_OF and spec["markers"][0]["sources"]
    ET.fromstring(uploads[0][v["preview"]].decode("utf-8"))


def test_a_tracker_compare_with_unusable_series_is_a_report_line_not_a_failed_day(store) -> None:
    wire = tc.TrackerCompareWire(title="t", caption="c", series=[tc.PickWire(id="px_brent"), tc.PickWire(id="nope")])
    secs, rep, _, uploads = _attach(visuals.VisualPlan(visuals=[_ask(form="tracker_compare")]), {"TrackerCompare": wire})
    assert rep["produced"] == 0 and "refused" in rep["skipped"][0] and "visuals" not in secs[0] and not uploads


# -- stills ----------------------------------------------------------------------------

def test_stills_are_valid_svg_even_when_bare(store) -> None:
    net = _network()
    ns.ground(net, _facts())
    ET.fromstring(graphs.network_svg(net))
    ET.fromstring(graphs.network_svg(ns.Network(title="t", caption="c", nodes=[], edges=[])))
    spec = _flowmap()
    fs.ground(spec, _facts())
    ET.fromstring(graphs.flow_svg(spec))
    ET.fromstring(graphs.flow_svg(fs.FlowMap(title="t", caption="c", places=[], flows=[])))
    cmp_ = _compare("chk_hormuz_transits", "chk_hormuz_tanker_transits")
    tc.ground(cmp_, _facts(), AS_OF)
    ET.fromstring(graphs.tracker_compare_svg(cmp_))
    ET.fromstring(graphs.tracker_compare_svg(tc.TrackerCompare(title="t", caption="c", series=[])))


# -- visuals-only ----------------------------------------------------------------------

def test_visuals_only_regenerates_today_as_a_network(tmp_path, monkeypatch) -> None:
    monkeypatch.setattr(daily, "daily_dir", lambda _d: tmp_path)
    record = {"schema": 1, "domain": "geopolitics", "date": AS_OF, "summary": {"headline": "H", "the_day": []}, "theaters": _sections()}
    (tmp_path / f"{AS_OF}.json").write_text(json.dumps(record), encoding="utf-8")

    def ask(schema, role, task):
        return visuals.VisualPlan(visuals=[_ask()]) if schema is visuals.VisualPlan else _network()

    def no_harness(*_a, **_k):
        raise AssertionError("harness used")

    out = daily_visuals.redo(None, None, "geopolitics", AS_OF, fresh=True, ask=ask, ready=no_harness, runner=no_harness,
                             uploader=lambda files: {"ok": True, "failed": []})
    assert out["produced"] == 1, out
    saved = json.loads((tmp_path / f"{AS_OF}.json").read_text(encoding="utf-8"))
    assert saved["theaters"][0]["visuals"][0]["kind"] == "network"
