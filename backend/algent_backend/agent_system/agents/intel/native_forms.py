"""
Producing the native interactive visual forms (``timeline``, ``mapstory``): from the planner's ask to a hosted spec
JSON plus an SVG still, in the shape of ``scene3d.produce``.

Why a structured model call and not the coding harness: these forms are DATA (``timeline_spec``, ``mapstory_spec``);
the site draws them natively and interactively. The model fills a typed schema, the contract validates it against
the cited facts mechanically (dates, places, figures, words), and nothing is executed. No subscription CLI is
needed, so these forms do not depend on the harness being ready. Cost: one house-model call per visual.
"""

from __future__ import annotations

import json
from collections.abc import Callable
from typing import Any

from . import mapstory_spec as ms
from . import native_preview, timeline_spec as ts
from . import visuals_facts as vf

NATIVE_FORMS = ("timeline", "mapstory")
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
the hour. `place` (name, and lat/lon only if you are sure of them) only when where it happened matters. Use `lanes`
(2 to 4: an actor or a thread, with `lane` on each event) only when parallel threads are the understanding; otherwise
none. Leave `sources`, `now` and `alt` empty. `title` states the finding ("Strikes tripled in four days"), `caption`
is one plain sentence for the reader.
"""

MAPSTORY_ROLE = """\
You build one MAP STORY: an animated sequence over a map that lets a reader watch what moved where and when.
""" + _COMMON + """\
Steps (2 to 12), in date order: each has a `date`, a `caption` of at most 35 words saying what CHANGED at that step,
`fact_ids`, and `show`: the features that appear or change at this step; state carries forward, so list only what is
new or moved, and `hide` the ids that should disappear. Features, each with a short `label` (at most 6 words), a
`tone` (accent, hot, warn, cool, good, ink) and the NAMED `place` it is at (a route lists `places`, its named
stops); the name must be a place a cited fact speaks of, and the coordinates (lat and lon in degrees) must be where
that place really is:
- point: a unit, site, strike or event at `at`. Showing the same id again at a new place MOVES it (it glides).
- route: `path` of waypoints in travel order (a drawn arrow, direction = order) for a movement the facts describe.
- area: `ring`, an outline (3 to 40 points) of territory a fact says is held, contested or affected.
- range: `at` and `radius_km`, a range ring, only when a cited fact states that radius in km.
Keep it simple enough to read at a glance: a handful of features, one idea per step. Leave `bounds`, `sources`
and `alt` empty.
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


_FORMS: dict[str, tuple[type, str, Callable[..., tuple[list[str], str]]]] = {
    "timeline": (ts.Timeline, TIMELINE_ROLE, _build_timeline),
    "mapstory": (ms.MapStory, MAPSTORY_ROLE, _build_mapstory),
}


def produce(form: str, brief: Any, cited: list[vf.Fact], n: int, *, domain: str, as_of: str, site_dir: str,
            ask: Callable[[Any, str, str], Any], uploader: Callable[[dict[str, bytes]], dict],
            report: dict | None = None) -> dict | None:
    """One native visual, planned to hosted. Returns the visual's record, or None with the reason in
    ``report["skipped"]``. Facts dropped by the contract are named in ``report["trimmed"]``. Never raises."""
    tag = f"{brief.theater_id}/{form}"
    rep = report if report is not None else {}
    skip = rep.setdefault("skipped", [])
    schema, role, build = _FORMS[form]
    by_id = {f.id: f for f in cited}
    try:
        spec = ask(schema, role, _facts_message(brief, cited))
        if not isinstance(spec, schema):
            skip.append(f"{tag}: no {form} returned")
            return None
        notes, svg = build(spec, by_id, as_of)
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
    ids = [i for obj in (spec.events if form == "timeline" else spec.steps) for i in obj.fact_ids]
    return {"id": vid, "kind": form, "title": spec.title, "caption": spec.caption, "reader_question": brief.reader_question,
            "asset": preview_path, "raster": "", "spec": spec_path, "preview": preview_path, "schematic": False,
            "as_of": as_of, "ai_label": "", "sources": _sources(list(dict.fromkeys(ids)), by_id), "detail": spec.alt,
            "generator": "native", "model": ""}
