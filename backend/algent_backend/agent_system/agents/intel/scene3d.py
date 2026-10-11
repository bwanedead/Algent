"""
Producing a ``scene3d`` daily visual: from the planner's ask to a hosted scene JSON plus a PNG still.

Why a structured model call and not the coding harness: a scene is DATA (``scene_spec.Scene``), so the model fills
a typed schema and the contract validates it mechanically (every size traceable, limits, timeline). A harness
would write free-form files we would then have to re-parse and trust; here nothing is executed. No subscription
CLI is needed, so a scene does not even depend on the harness being ready. Cost: one house-model call per scene.

Natural Earth coastlines are resolved here (``geo``), so the published JSON is self-contained.
"""

from __future__ import annotations

import json
from collections.abc import Callable
from typing import Any

from . import flags, geo, scene_preview, scene_spec as ss
from . import visuals_facts as vf

SCENE_ROLE = """\
You build one interactive 3D scene a reader can rotate, zoom and scrub through time, as JSON in the given schema.
Data only; the site draws it. Coordinates: x east, y north, z up, in `unit`. Build ONLY what the brief says and
the sources support; keep it modest (a few dozen objects), because it runs on a phone.

Every `real` object (a vessel, aircraft, structure, range, lane) sets `cite` to one of your `sources`, and EVERY
size number it carries (length, radius, height, range, depth, apex) must appear in that source's `says` text, in
the source's units or a plain conversion of them. A source is a fact of the day (`fact_id`, `says` copied from it)
or, only if the brief gives a source hint, a named public specification (`url` and the passage in `says`). Do
not invent a dimension, position, range or capability. A drawing aid that measures nothing is `real: false`, and a
scene containing invented-shape detail sets `schematic: true`. Coastlines: add a `coast` object with
`bbox_lonlat` and `origin`; do not draw coastlines by hand. Place things by `lonlat` when the scene has an origin.

`title` is the finding, `caption` one plain sentence to the reader, neither with a number your sources lack.
Give 2-4 `cameras` (an overview, a close one, a plan view), a `scale_bar` whose length is a round number in
`unit`, labels short and direct on the objects, and a `timeline` ONLY when change over dated frames is the point
(each frame cites its source). Colour is a palette token, never a hex value.
"""


def _clip(ring: list[tuple[float, float]], box: tuple[float, float, float, float]) -> list[tuple[float, float]]:
    """Sutherland-Hodgman against an axis-aligned lon/lat box."""
    w, s, e, n = box
    edges: list[Callable[[tuple[float, float]], bool]] = [lambda p: p[0] >= w, lambda p: p[0] <= e,
                                                           lambda p: p[1] >= s, lambda p: p[1] <= n]
    def cut(a: tuple[float, float], b: tuple[float, float], i: int) -> tuple[float, float]:
        v = (w, e, s, n)[i]
        if i < 2:
            t = (v - a[0]) / ((b[0] - a[0]) or 1e-12)
            return v, a[1] + t * (b[1] - a[1])
        t = (v - a[1]) / ((b[1] - a[1]) or 1e-12)
        return a[0] + t * (b[0] - a[0]), v
    out = ring
    for i, inside in enumerate(edges):
        src, out = out, []
        for j, cur in enumerate(src):
            prev = src[j - 1]
            if inside(cur):
                if not inside(prev):
                    out.append(cut(prev, cur, i))
                out.append(cur)
            elif inside(prev):
                out.append(cut(prev, cur, i))
        if not out:
            break
    return out


def fill_coasts(scene: ss.Scene, countries: list[geo.Country] | None, max_ring: int = 220) -> list[str]:
    """Fill every ``coast`` object's polygons from Natural Earth. Returns problems (no data, nothing in frame)."""
    problems = []
    for o in scene.objects:
        if not isinstance(o, ss.Coast) or o.polygons:
            continue
        if scene.origin is None:
            problems.append(f"{o.id}: coast needs a scene origin")
            continue
        if not countries:
            problems.append(f"{o.id}: no Natural Earth data on this machine")
            continue
        w, s, e, n = o.bbox_lonlat
        for c in countries:
            if c.bbox[2] < w or c.bbox[0] > e or c.bbox[3] < s or c.bbox[1] > n:
                continue
            for poly in c.polygons:
                clipped = _clip(poly[0], (w, s, e, n))
                if len(clipped) < 3:
                    continue
                step = max(1, len(clipped) // max_ring)
                o.polygons.append([[round(v, 2) for v in ss.lonlat_to_xy(x, y, scene.origin, scene.unit)]
                                   for x, y in clipped[::step]])
        if not o.polygons:
            problems.append(f"{o.id}: no land inside {o.bbox_lonlat}")
    return problems


def alt_text(scene: ss.Scene) -> str:
    """A plain listing of what is in the scene and how big, for readers who cannot see or turn it."""
    bits = []
    for o in scene.objects:
        if isinstance(o, ss.Coast):
            continue
        dims = ", ".join(f"{k} {v:g} {scene.unit}" for k, v in ss._sizes(o))
        bits.append(f"{o.label or o.id} ({o.type}{', ' + dims if dims else ''})")
    return f"{scene.title}. {scene.caption} Contains: " + "; ".join(bits) + "."


def _message(brief: Any, cited: list[vf.Fact]) -> str:
    lines = "\n".join(f"[{f.id}] {f.text[:600]}" for f in cited)
    hint = (brief.source_hint or "").strip()
    return (f"BRIEF (finding): {brief.finding}\nQuestion answered: {brief.reader_question}\nWhat to build: {brief.spec}\n"
            f"Caption intent: {brief.caption}\n\nFACTS OF THE DAY (the only numbers you may use, unless a source hint):\n{lines}\n\n"
            + (f"SOURCE HINT (a public specification you may cite for sizes; quote its passage in `says`): {hint}\n\n" if hint else "")
            + "TASK: produce the scene.")


def _srcs(scene: ss.Scene, cited: list[vf.Fact]) -> list[dict]:
    seen: dict[str, str] = {}
    for s in scene.sources:
        if s.url:
            seen.setdefault(s.url, s.label)
        for f in cited:
            if f.id == s.fact_id:
                for raw in f.sources:
                    label, url = vf.source_label(raw)
                    seen.setdefault(url or label, label)
    for c in scene.objects:
        if isinstance(c, ss.Coast):
            seen.setdefault("Natural Earth", "Natural Earth (public domain)")
    return [{"label": label, "url": url if url.startswith("http") else ""} for url, label in seen.items()]


def produce(brief: Any, cited: list[vf.Fact], n: int, *, domain: str, as_of: str, site_dir: str,
            ask: Callable[[Any, str, str], Any], uploader: Callable[[dict[str, bytes]], dict],
            countries: list[geo.Country] | None = None, report: dict | None = None) -> dict | None:
    """One scene, planned to hosted. Returns the visual's record, or None with the reason in ``report["skipped"]``.
    Never raises."""
    tag = f"{brief.theater_id}/scene3d"
    skip = (report or {}).setdefault("skipped", [])
    try:
        scene = ask(ss.Scene, SCENE_ROLE, _message(brief, cited))
        if not isinstance(scene, ss.Scene):
            skip.append(f"{tag}: no scene returned")
            return None
        ss.normalize(scene)
        problems = fill_coasts(scene, countries if countries is not None else geo.load())
        mo, mv = flags.scene3d_limits()
        public = flags.scene3d_public_specs() and bool((brief.source_hint or "").strip())
        problems += ss.validate_scene(scene, {f.id: f.text for f in cited}, allow_public=public,
                                      max_objects=mo, max_vertices=mv)
        if problems:
            skip.append(f"{tag}: scene refused: " + "; ".join(problems[:4]))
            return None
        scene.alt = scene.alt or alt_text(scene)
        png = scene_preview.render(scene.model_dump(mode="json"))
    except Exception as exc:  # noqa: BLE001 - a scene is an addition to the day, never its gate
        skip.append(f"{tag}: scene failed: {type(exc).__name__}: {str(exc)[:140]}")
        return None
    vid = f"anx_dv{as_of.replace('-', '')}_{n}"
    base = f"{site_dir}/{domain}/{as_of}"
    scene_path, preview_path = f"{base}/{vid}.scene.json", f"{base}/{vid}.png"
    sent = uploader({scene_path: json.dumps(scene.model_dump(mode="json"), separators=(",", ":")).encode("utf-8"),
                     preview_path: png})
    if not sent.get("ok", True) or sent.get("note") or sent.get("failed"):
        skip.append(f"{tag}: not hosted ({sent.get('note') or sent.get('failed')})")
        return None
    return {"id": vid, "kind": "scene3d", "title": scene.title, "caption": scene.caption,
            "reader_question": brief.reader_question, "asset": preview_path, "raster": preview_path,
            "scene": scene_path, "preview": preview_path, "schematic": scene.schematic, "as_of": as_of,
            "ai_label": "", "sources": _srcs(scene, cited), "detail": scene.alt, "generator": "scene3d",
            "model": ""}
