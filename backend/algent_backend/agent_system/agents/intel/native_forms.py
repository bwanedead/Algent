"""
Producing the native interactive visual forms (``timeline``, ``mapstory``, ``network``, ``flow``,
``tracker_compare``): from the planner's ask to a hosted spec JSON plus an SVG still, in the shape of
``scene3d.produce``.

Why a structured model call and not the coding harness: these forms are DATA (``timeline_spec``, ``mapstory_spec``,
``network_spec``, ``flow_spec``, ``tracker_compare_spec``); the site draws them natively and interactively. The model
fills a typed schema, the contract validates it against the cited facts mechanically (dates, places, ends of a
relation, figures, words), and nothing is executed. ``tracker_compare`` takes no figure from a model at all: the
model names instrument series and the contract reads their points from the instruments store. No subscription CLI
is needed, so these forms do not depend on the harness being ready. Cost: one house-model call per visual.
"""

from __future__ import annotations

import json
from collections.abc import Callable
from typing import Any

from . import flow_spec as fs
from . import mapstory_spec as ms
from . import native_preview, native_preview_graphs as graphs, timeline_spec as ts
from . import network_spec as ns
from . import tracker_compare_spec as tc
from . import visuals_facts as vf

NATIVE_FORMS = ("timeline", "mapstory", "network", "flow", "tracker_compare")
FACT_CHARS = 600

_COMMON = """\
Data only; the site draws it. Build ONLY from the FACTS given (each has an id): every event or step cites the facts
that state it in `fact_ids`; its date must be stated by one of them (the facts' own dates, written YYYY-MM-DD); put
no number of your own in any text (a figure appears only if a cited fact holds it, written the same way). Do not
infer, round, or fill gaps; what the facts do not say is not drawn. Words are for a reader on a phone: plain,
concrete, no jargon, no 'the reader'. Anything that fails the check is dropped, so fewer, sure items beat many.
"""

TIMELINE_ROLE = """\
You build one TIMELINE a reader scans top to bottom to grasp a sequence: who did what, in what order, how fast.
""" + _COMMON + """\
Events (3 to 24, only the ones that carry the sequence): `title` is the event in at most 10 words, `detail` one
plain line of at most 30 words (what, where, why it mattered, only from the facts), `kind` one of strike, statement,
meeting, decision, movement, deadline, other. `actors` are ISO alpha-2 country codes (RU, UA, US...) of who acted,
at most 4, none for a non-state actor you cannot code. `date` is YYYY-MM-DD; add `time` HH:MM only when a fact gives
the hour. `place_name` (and `place_located` true with `place_lat`/`place_lon` only if you are sure of them) only when where it
happened matters. Use `lanes`
(2 to 4: an actor or a thread, with `lane` on each event) only when parallel threads are the understanding; otherwise
none. Leave `sources`, `now` and `alt` empty. `title` states the finding ("Strikes tripled in four days"), `caption`
is one plain sentence for the reader.
"""

MAPSTORY_ROLE = """\
You build one MAP STORY: an animated sequence over a map that lets a reader watch what moved where and when.
""" + _COMMON + """\
Steps (2 to 12), in date order: each has a `date`, a `caption` of at most 35 words saying what CHANGED at that step,
`fact_ids`, and `show`: the features that appear or change at this step; state carries forward, so list only what is
new or moved, and `hide` the ids that should disappear. Every feature is one object with an `id`, a `kind`, a short `label` (at most 6
words), a `tone` (accent, hot, warn, cool, good, ink) and the NAMED `place` it is at (a route lists `places`, its
named stops); the name must be a place a cited fact speaks of, and the coordinates (lat and lon in degrees) must be
where that place really is. Fill only the fields of its kind and leave the rest empty:
- kind point: a unit, site, strike or event; `at` holds its one position. Showing the same id again at a new place MOVES it.
- kind route: `path` of waypoints in travel order (a drawn arrow, direction = order) for a movement the facts describe.
- kind area: `ring`, an outline (3 to 40 points) of territory a fact says is held, contested or affected.
- kind range: `at` (one position) and `radius_km`, a range ring, only when a cited fact states that radius in km.
Keep it simple enough to read at a glance: a handful of features, one idea per step. Leave `bounds`, `sources`
and `alt` empty.
"""


NETWORK_ROLE = """\nYou build one LIVING NETWORK: who backs, funds, arms, opposes, attacks, sanctions, trades with or depends on whom,
drawn so a reader sees the shape of a web of relations that prose makes tedious.
""" + _COMMON + """Nodes (3 to 16, only those that carry the picture): `id`, a plain `label` of at most 5 words that a cited fact uses
(the check looks for the name in the facts), a `kind` (state, group, person, org, place) and, for a state or
something belonging to one, its alpha-2 `iso`. Give `weight` (node size) only when a fact states one comparable
figure for those nodes, set `weight_label` to what it measures, and cite that fact in the node's `fact_ids`;
otherwise leave both empty.
Edges (3 to 30): `source` and `target` are node ids; `relation` is one of supports, arms, funds, allied_with,
opposes, attacks, sanctions, trades, depends_on, negotiates_with; `direction` is forward (source acts on target) or
both. A cited fact must state the relation and name BOTH ends. `detail` is at most 20 words, from the facts only.
`strength` is 1 (minor), 2 (clear) or 3 only where a fact stresses scale (largest, main, billions).
Time: `start`/`end` (YYYY-MM-DD, each stated by a cited fact) only when a relation begins or ends inside the story;
then the reader gets a scrubber. A relation that changes is an ending edge plus a new one. Otherwise leave them empty.
Prefer a web with a clear centre and a few clusters to every link you can find. Leave `sources` and `alt` empty.
"""

FLOW_ROLE = """\nYou build one FLOW MAP: goods, energy, money, weapons or people moving between places, drawn as arcs a reader can
follow, and what happens when a route breaks.
""" + _COMMON + """Places (2 to 14): `id`, a `name` of at most 4 words that a cited fact uses, a `role` (source, sink, hub,
chokepoint) and its `lat`/`lon` in degrees, where that place really is.
Flows (2 to 24): `source` and `target` are place ids, `commodity` at most 4 words, `via` the chokepoint or hub ids it
passes in travel order. A cited fact must state the movement and name its ends. Give `amount`, `unit` and `period`
(for example 2.1, "million barrels a day") only if a cited fact states that figure, written the same way; otherwise
leave `amount` 0, the flow is drawn without a width. `detail` at most 20 words.
Disruptions (0 to 3) when a fact says a route or place stops, closes or is attacked: `date` stated by a cited fact,
`breaks` the ids of the flows or places that stop, `reroutes` the ids of flows that carry the traffic instead (these
are ordinary flows you also list, each stated by its own cited fact, shown only while the disruption is on), `effect`
at most 30 words from the facts. No disruption unless the facts hold one. Leave `bounds`, `sources` and `alt` empty.
"""

TRACKER_ROLE = """\nYou build one TRACKER COMPARISON: several of OUR OWN measured series on one chart, so a reader sees how
a physical flow, a price and a count moved together or apart. You write NO numbers: the chart is drawn from our store.
Markers cite the FACTS given (each has an id); put no number of your own in any text. Words are for a reader on a
phone: plain, concrete, no jargon. Anything that fails the check is dropped, so fewer, sure items beat many.
Choose 2 to 6 series by exact `id` from the list given (series that share a cause or an effect and tell one story,
not whatever exists), give each a plain `label` of at most 4 words with no digits, and set `window_days` (30, 60, 90,
180 or 365) to the span that shows the story. `markers` (0 to 6) are developments from the FACTS that explain the
movement: each a `date` stated by a cited fact, a `label` of at most 8 words, and its `fact_ids`; none where the
facts give no dated cause. `title` states the finding in words ("Transits fell as tanker counts rose"), `caption` one
plain sentence. Any series id not in the list, or an internal-only source, is dropped.
"""


def _facts_message(brief: Any, cited: list[vf.Fact]) -> str:
    lines = "\n".join(f"[{f.id}] {f.text[:FACT_CHARS]}" for f in cited)
    return (f"BRIEF (finding): {brief.finding}\nQuestion answered: {brief.reader_question}\nWhat to build: {brief.spec}\n"
            f"Caption intent: {brief.caption}\n\nFACTS (cite by id; the only things you may state):\n{lines}\n\nTASK: produce it.")


def _sources(fact_ids: list[str], by_id: dict[str, vf.Fact]) -> list[dict]:
    seen: dict[str, str] = {}
    for i in fact_ids:
        for raw in (by_id[i].sources if i in by_id else []):
            label, url = vf.source_label(raw)
            seen.setdefault(url or label, label)
    return [{"label": label, "url": url if url.startswith("http") else ""} for url, label in seen.items()]


def _merge(a: list[dict], b: list[dict]) -> list[dict]:
    seen = {x["url"] or x["label"] for x in a}
    return a + [x for x in b if (x["url"] or x["label"]) not in seen and not seen.add(x["url"] or x["label"])]


def _build_timeline(spec: ts.Timeline, by_id: dict[str, vf.Fact], as_of: str) -> tuple[list[str], str]:
    notes = ts.ground(spec, {k: f.text for k, f in by_id.items()})
    for e in spec.events:
        e.sources = [ts.Source(**s) for s in _sources(e.fact_ids, by_id)]
    spec.now, spec.alt = as_of, ts.alt_text(spec)
    return notes, native_preview.timeline_svg(spec)


def _build_mapstory(spec: ms.MapStory, by_id: dict[str, vf.Fact], as_of: str) -> tuple[list[str], str]:
    notes = ms.ground(spec, {k: f.text for k, f in by_id.items()})
    for s in spec.steps:
        s.sources = [ts.Source(**x) for x in _sources(s.fact_ids, by_id)]
    spec.alt = ms.alt_text(spec)
    return notes, native_preview.mapstory_svg(spec)


def _build_network(spec: ns.Network, by_id: dict[str, vf.Fact], as_of: str) -> tuple[list[str], str]:
    notes = ns.ground(spec, {k: f.text for k, f in by_id.items()})
    for e in spec.edges:
        e.sources = [ts.Source(**x) for x in _sources(e.fact_ids, by_id)]
    spec.alt = ns.alt_text(spec)
    return notes, graphs.network_svg(spec)


def _build_flow(spec: fs.FlowMap, by_id: dict[str, vf.Fact], as_of: str) -> tuple[list[str], str]:
    notes = fs.ground(spec, {k: f.text for k, f in by_id.items()})
    for obj in (*spec.flows, *spec.disruptions):
        obj.sources = [ts.Source(**x) for x in _sources(obj.fact_ids, by_id)]
    spec.alt = fs.alt_text(spec)
    return notes, graphs.flow_svg(spec)


def _build_tracker_compare(spec: tc.TrackerCompare, by_id: dict[str, vf.Fact], as_of: str) -> tuple[list[str], str]:
    notes = tc.ground(spec, {k: f.text for k, f in by_id.items()}, as_of)
    for m in spec.markers:
        m.sources = [ts.Source(**x) for x in _sources(m.fact_ids, by_id)]
    spec.alt = tc.alt_text(spec)
    return notes, graphs.tracker_compare_svg(spec)


#: form -> (strict spec class, SVG still builder): rebuild a still from a SAVED spec with no model call (``visuals_store.republish``).
_STILLS: dict[str, tuple[type, Callable[[Any], str]]] = {
    "timeline": (ts.Timeline, native_preview.timeline_svg), "mapstory": (ms.MapStory, native_preview.mapstory_svg),
    "network": (ns.Network, graphs.network_svg), "flow": (fs.FlowMap, graphs.flow_svg),
    "tracker_compare": (tc.TrackerCompare, graphs.tracker_compare_svg),
}


def redraw_still(form: str, spec: dict[str, Any]) -> str:
    """The SVG still of a saved native spec (the JSON ``produce`` published), drawn with today's renderer."""
    cls, draw = _STILLS[form]
    return draw(cls.model_validate(spec))


def _fact_ids(spec: Any) -> list[str]:
    """Every fact id a built spec cites, in order."""
    objs = [*getattr(spec, "events", []), *getattr(spec, "steps", []), *getattr(spec, "nodes", []), *getattr(spec, "edges", []),
            *getattr(spec, "flows", []), *getattr(spec, "disruptions", []), *getattr(spec, "markers", [])]
    return [i for o in objs for i in getattr(o, "fact_ids", [])]


def _own_sources(spec: Any) -> list[dict]:
    """Sources the contract itself holds (the instruments behind a tracker comparison), not from any fact."""
    return [{"label": ln.source, "url": ln.source_url} for ln in getattr(spec, "series", []) if getattr(ln, "source", "")]


def _tracker_context(as_of: str) -> str:
    return tc.available_block(as_of)


# form -> (wire schema the model fills, wire -> strict spec, strict spec class, role, builder, extra context for the
# model). The wire schema has no unions (the house provider rejects oneOf/anyOf); a fake or test may hand back the
# strict spec directly.
_FORMS: dict[str, tuple[type, Callable[[Any], tuple[Any, list[str]]], type, str, Callable[..., tuple[list[str], str]],
                        Callable[[str], str] | None]] = {
    "timeline": (ts.TimelineWire, ts.from_wire, ts.Timeline, TIMELINE_ROLE, _build_timeline, None),
    "mapstory": (ms.MapStoryWire, ms.from_wire, ms.MapStory, MAPSTORY_ROLE, _build_mapstory, None),
    "network": (ns.NetworkWire, ns.from_wire, ns.Network, NETWORK_ROLE, _build_network, None),
    "flow": (fs.FlowWire, fs.from_wire, fs.FlowMap, FLOW_ROLE, _build_flow, None),
    "tracker_compare": (tc.TrackerCompareWire, tc.from_wire, tc.TrackerCompare, TRACKER_ROLE, _build_tracker_compare, _tracker_context),
}


def produce(form: str, brief: Any, cited: list[vf.Fact], n: int, *, domain: str, as_of: str, site_dir: str,
            ask: Callable[[Any, str, str], Any], uploader: Callable[[dict[str, bytes]], dict],
            report: dict | None = None) -> dict | None:
    """One native visual, planned to hosted. Returns the visual's record, or None with the reason in
    ``report["skipped"]``. Facts dropped by the contract are named in ``report["trimmed"]``. Never raises."""
    tag = f"{brief.theater_id}/{form}"
    rep = report if report is not None else {}
    skip = rep.setdefault("skipped", [])
    wire_schema, from_wire, strict, role, build, context = _FORMS[form]
    by_id = {f.id: f for f in cited}
    try:
        extra = "\n\n" + context(as_of) if context else ""
        got = ask(wire_schema, role, _facts_message(brief, cited) + extra)
        pre: list[str] = []
        if isinstance(got, wire_schema):
            spec, pre = from_wire(got)
        else:
            spec = got
        if not isinstance(spec, strict):
            skip.append(f"{tag}: no {form} returned")
            return None
        notes, svg = build(spec, by_id, as_of)
        notes = pre + notes
        if bad := ts.refused(notes):
            skip.append(f"{tag}: {form} refused: " + "; ".join(b.removeprefix("REFUSED: ") for b in bad[:3]))
            return None
        if notes:
            rep.setdefault("trimmed", []).extend(f"{tag}: {x}" for x in notes[:6])
    except Exception as exc:  # noqa: BLE001 - a visual is an addition to the day, never its gate
        skip.append(f"{tag}: {form} failed: {type(exc).__name__}: {str(exc)[:140]}")
        return None
    vid = f"anx_dv{as_of.replace('-', '')}_{n}"
    base = f"{site_dir}/{domain}/{as_of}"
    spec_path, preview_path = f"{base}/{vid}.{form}.json", f"{base}/{vid}.{form}.svg"
    sent = uploader({spec_path: json.dumps(spec.model_dump(mode="json"), separators=(",", ":")).encode("utf-8"),
                     preview_path: svg.encode("utf-8")})
    if not sent.get("ok", True) or sent.get("note") or sent.get("failed"):
        skip.append(f"{tag}: not hosted ({sent.get('note') or sent.get('failed')})")
        return None
    return {"id": vid, "kind": form, "title": spec.title, "caption": spec.caption, "reader_question": brief.reader_question,
            "asset": preview_path, "raster": "", "spec": spec_path, "preview": preview_path, "schematic": False,
            "as_of": as_of, "ai_label": "", "sources": _merge(_sources(list(dict.fromkeys(_fact_ids(spec))), by_id), _own_sources(spec)), "detail": spec.alt,
            "generator": "native", "model": ""}
