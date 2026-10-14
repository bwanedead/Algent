"""
Server-side SVG stills for the native visual forms: what a link preview, a social card and a no-script reader get
in place of the interactive figure (``components/NativeTimeline.tsx``, ``MapStory.tsx``). Plain SVG text, no
dependency; light paper palette. Deliberately simple: the interactive form is the real thing.
"""

from __future__ import annotations

import math
import textwrap
from xml.sax.saxutils import escape

from . import geo
from .mapstory_spec import Area, MapStory, Point, Range, Route
from .timeline_spec import Timeline

PAPER, INK, MUTED, RULE = "#f4f1ea", "#1b1b1b", "#6b6b66", "#a8a59b"
TONE = {"ink": "#1b1b1b", "accent": "#b3361b", "warn": "#d98e04", "cool": "#2f6f9f", "hot": "#c8321e", "good": "#3d7a4a"}
W = 640
_FONT = 'font-family="Helvetica,Arial,sans-serif"'


def _svg(w: int, h: int, body: str, label: str) -> str:
    return (f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {w} {h}" width="{w}" height="{h}" role="img" '
            f'aria-label="{escape(label, {chr(34): "&quot;"})}"><rect width="{w}" height="{h}" fill="{PAPER}"/>{body}</svg>')


def _text(x: float, y: float, s: str, size: int = 13, fill: str = INK, weight: str = "400", anchor: str = "start") -> str:
    return f'<text x="{x:g}" y="{y:g}" font-size="{size}" fill="{fill}" font-weight="{weight}" text-anchor="{anchor}" {_FONT}>{escape(s)}</text>'


def timeline_svg(tl: Timeline) -> str:
    """Vertical spine, a dot and a card per event, in order. Spacing is even: the interactive form has the time scale."""
    x_date, x_spine, x_text = 18, 112, 132
    y, parts = 54.0, [_text(18, 26, tl.title, 17, weight="700")]
    top = y
    for e in tl.events:
        title = textwrap.wrap(e.title, 58) or [""]
        detail = textwrap.wrap(e.detail, 70)[:3]
        parts.append(f'<circle cx="{x_spine}" cy="{y - 4:g}" r="5" fill="{PAPER}" stroke="{INK}" stroke-width="2"/>')
        parts.append(_text(x_date, y, e.date[5:] if len(e.date) == 10 else e.date, 12, MUTED))
        parts.append(_text(x_text, y, title[0], 14, weight="700"))
        y += 16
        for line in title[1:] + detail:
            parts.append(_text(x_text, y, line, 12, MUTED if line in detail else INK))
            y += 15
        y += 14
    parts.insert(1, f'<line x1="{x_spine}" y1="{top - 4:g}" x2="{x_spine}" y2="{y - 24:g}" stroke="{RULE}" stroke-width="2"/>')
    return _svg(W, int(y + 8), "".join(parts), f"Timeline: {tl.title}")


def _land(frame: list[float], px) -> str:
    countries = geo.load() or []
    w, s, e, n = frame
    out = []
    for c in countries:
        if c.bbox[2] < w or c.bbox[0] > e or c.bbox[3] < s or c.bbox[1] > n:
            continue
        for poly in c.polygons:
            step = max(1, len(poly[0]) // 160)
            pts = " ".join(f"{px(x, y)[0]:.1f},{px(x, y)[1]:.1f}" for x, y in poly[0][::step])
            out.append(f'<polygon points="{pts}" fill="#dcd6c4" stroke="#bdb7a4" stroke-width="0.6"/>')
    return "".join(out)


def mapstory_svg(story: MapStory) -> str:
    """Every feature of the story on one frame, each as of the last step that shows it."""
    if len(story.bounds) != 4:
        return _svg(W, 60, _text(18, 34, story.title, 15, weight="700"), f"Map story: {story.title}")
    w, s, e, n = story.bounds
    height = int(min(520, max(240, W * (n - s) / max(e - w, 1e-6))))
    kx, ky = W / max(e - w, 1e-6), height / max(n - s, 1e-6)
    k = min(kx, ky)
    ox, oy = (W - (e - w) * k) / 2, (height - (n - s) * k) / 2

    def px(lon: float, lat: float) -> tuple[float, float]:
        return ox + (lon - w) * k, oy + (n - lat) * k

    last: dict[str, tuple[int, object]] = {}
    for i, st in enumerate(story.steps, 1):
        for f in st.show:
            last[f.id] = (i, f)
    body = [f'<clipPath id="c"><rect width="{W}" height="{height}"/></clipPath><g clip-path="url(#c)">', _land(story.bounds, px)]
    marks = []
    for _, f in last.values():
        col = TONE.get(f.tone, TONE["accent"])
        if isinstance(f, Area):
            pts = " ".join("%.1f,%.1f" % px(p.lon, p.lat) for p in f.ring)
            body.append(f'<polygon points="{pts}" fill="{col}" fill-opacity="0.2" stroke="{col}" stroke-width="1.5"/>')
        elif isinstance(f, Range):
            cx, cy = px(f.at.lon, f.at.lat)
            body.append(f'<circle cx="{cx:.1f}" cy="{cy:.1f}" r="{f.radius_km / 111.32 * k:.1f}" fill="{col}" fill-opacity="0.08" stroke="{col}" stroke-width="1.5" stroke-dasharray="5 4"/>')
        elif isinstance(f, Route):
            pts = [px(p.lon, p.lat) for p in f.path]
            body.append(f'<polyline points="{" ".join("%.1f,%.1f" % p for p in pts)}" fill="none" stroke="{col}" stroke-width="2.5" stroke-linecap="round"/>')
            if f.arrow:
                (x0, y0), (x1, y1) = pts[-2], pts[-1]
                a = math.atan2(y1 - y0, x1 - x0)
                tip = [(x1, y1), (x1 - 10 * math.cos(a - 0.45), y1 - 10 * math.sin(a - 0.45)), (x1 - 10 * math.cos(a + 0.45), y1 - 10 * math.sin(a + 0.45))]
                body.append(f'<polygon points="{" ".join("%.1f,%.1f" % p for p in tip)}" fill="{col}"/>')
            marks.append((f, pts[len(pts) // 2], col))
        elif isinstance(f, Point):
            x, y = px(f.at.lon, f.at.lat)
            body.append(f'<circle cx="{x:.1f}" cy="{y:.1f}" r="5" fill="{col}" stroke="#fff" stroke-width="1.5"/>')
            marks.append((f, (x, y), col))
    for f, (x, y), col in marks:
        if f.label:
            body.append(_text(x + 8, y - 7, f.label, 11, INK, "700").replace("<text", '<text stroke="#f4f1ea" stroke-width="3" paint-order="stroke"', 1))
    body.append("</g>")
    cap = textwrap.wrap(story.caption, 90)[:2]
    foot = "".join(_text(18, height + 22 + 16 * j, line, 12, MUTED) for j, line in enumerate(cap))
    return _svg(W, height + 28 + 16 * len(cap), "".join(body) + foot, f"Map: {story.title}")
