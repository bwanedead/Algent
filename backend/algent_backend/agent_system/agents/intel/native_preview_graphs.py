"""
Server-side SVG stills for the network, flow and tracker-comparison forms (``NativeNetwork.tsx``, ``NativeFlow.tsx``,
``NativeTrackerCompare.tsx``): what a link preview, an X card and a no-script reader get in place of the interactive
figure. Same palette and helpers as ``native_preview``; deliberately simple, the interactive form is the real thing.
"""

from __future__ import annotations

import math
import textwrap
from datetime import date

from .flow_spec import FlowMap
from .native_preview import INK, MUTED, RULE, W, land, map_frame, svg_doc, text_el
from .network_spec import FAMILY, Network
from .tracker_compare_spec import TrackerCompare, common_start

#: One colour per relation family (the site uses the matching --vl tokens) and one per tracker line.
FAMILY_COLOR = {"backing": "#2f6f9f", "hostile": "#c8321e", "exchange": "#b07a05", "talks": "#7a56c4"}
FAMILY_WORD = {"backing": "backs", "hostile": "opposes", "exchange": "trades or depends", "talks": "talks"}
LINE_COLORS = ("#b3361b", "#2f6f9f", "#3d7a4a", "#7a56c4", "#d98e04", "#1b1b1b")


def _arrow(x0: float, y0: float, x1: float, y1: float, col: str, size: float = 9) -> str:
    a = math.atan2(y1 - y0, x1 - x0)
    pts = [(x1, y1), (x1 - size * math.cos(a - 0.45), y1 - size * math.sin(a - 0.45)), (x1 - size * math.cos(a + 0.45), y1 - size * math.sin(a + 0.45))]
    return f'<polygon points="{" ".join("%.1f,%.1f" % p for p in pts)}" fill="{col}"/>'


def network_svg(net: Network) -> str:
    """Nodes on a circle, a coloured line per relation (an arrow where it points one way), a key of the families."""
    if not net.nodes:
        return svg_doc(W, 60, text_el(18, 34, net.title, 15, weight="700"), f"Network: {net.title}")
    h = 480
    cx, cy, rad = W / 2, 56 + (h - 100) / 2, min(W / 2 - 110, (h - 130) / 2)
    pos: dict[str, tuple[float, float]] = {}
    for i, n in enumerate(net.nodes):
        a = -math.pi / 2 + 2 * math.pi * i / len(net.nodes)
        pos[n.id] = (cx + rad * math.cos(a), cy + rad * math.sin(a))
    maxw = max((n.weight for n in net.nodes), default=0)
    body = [text_el(18, 26, net.title, 17, weight="700")]
    for e in net.edges:
        if e.source not in pos or e.target not in pos:
            continue
        (x0, y0), (x1, y1) = pos[e.source], pos[e.target]
        col = FAMILY_COLOR[FAMILY[e.relation]]
        d = math.hypot(x1 - x0, y1 - y0) or 1
        ux, uy = (x1 - x0) / d, (y1 - y0) / d
        tx, ty = x1 - ux * 16, y1 - uy * 16
        body.append(f'<line x1="{x0:.1f}" y1="{y0:.1f}" x2="{tx:.1f}" y2="{ty:.1f}" stroke="{col}" stroke-width="{1 + e.strength:g}" stroke-opacity="0.75"'
                    + (' stroke-dasharray="6 4"' if e.start or e.end else "") + "/>")
        body.append(_arrow(x0, y0, tx + ux * 7, ty + uy * 7, col))
        if e.direction == "both":
            body.append(_arrow(x1, y1, x0 + ux * 23, y0 + uy * 23, col))
    for n in net.nodes:
        x, y = pos[n.id]
        r = 7 + (9 * math.sqrt(n.weight / maxw) if maxw and n.weight else 3)
        body.append(f'<circle cx="{x:.1f}" cy="{y:.1f}" r="{r:.1f}" fill="{INK}" stroke="#fff" stroke-width="2"/>')
        right = x >= cx
        body.append(text_el(x + (r + 5 if right else -r - 5), y + 4, n.label, 12, INK, "700", "start" if right else "end").replace(
            "<text", '<text stroke="#f4f1ea" stroke-width="3" paint-order="stroke"', 1))
    used = {FAMILY[e.relation] for e in net.edges}
    kx = 18
    for fam in ("backing", "hostile", "exchange", "talks"):
        if fam in used:
            body.append(f'<rect x="{kx}" y="{h - 26}" width="16" height="4" fill="{FAMILY_COLOR[fam]}"/>' + text_el(kx + 22, h - 20, FAMILY_WORD[fam], 12, MUTED))
            kx += 40 + 7 * len(FAMILY_WORD[fam])
    cap = textwrap.wrap(net.caption, 90)[:2]
    foot = "".join(text_el(18, h + 6 + 16 * j, line, 12, MUTED) for j, line in enumerate(cap))
    return svg_doc(W, h + 14 + 16 * len(cap), "".join(body) + foot, f"Network: {net.title}")


def _arc(p0: tuple[float, float], p1: tuple[float, float]) -> tuple[str, tuple[float, float]]:
    """A quadratic arc between two points, bowed to the left of travel; also its midpoint."""
    mx, my = (p0[0] + p1[0]) / 2, (p0[1] + p1[1]) / 2
    dx, dy = p1[0] - p0[0], p1[1] - p0[1]
    cx, cy = mx + dy * 0.18, my - dx * 0.18
    return f"M{p0[0]:.1f},{p0[1]:.1f} Q{cx:.1f},{cy:.1f} {p1[0]:.1f},{p1[1]:.1f}", (0.25 * p0[0] + 0.5 * cx + 0.25 * p1[0], 0.25 * p0[1] + 0.5 * cy + 0.25 * p1[1])


def width_of(spec: FlowMap) -> dict[str, float]:
    """Line width in pixels per flow: in proportion to the amount among flows sharing a unit; 2.5 where no figure is stated."""
    out = {f.id: 2.5 for f in spec.flows}
    by_unit: dict[str, list] = {}
    for f in spec.flows:
        if f.amount:
            by_unit.setdefault(f.unit.lower(), []).append(f)
    for fs in by_unit.values():
        top = max(f.amount for f in fs)
        for f in fs:
            out[f.id] = round(1.5 + 8 * f.amount / top, 1) if len(fs) > 1 else 5.0
    return out


def flow_svg(spec: FlowMap) -> str:
    """Land, an arc per flow (width by amount), the places, and the broken routes dashed in red."""
    if len(spec.bounds) != 4:
        return svg_doc(W, 60, text_el(18, 34, spec.title, 15, weight="700"), f"Flows: {spec.title}")
    height, _, px = map_frame(spec.bounds)
    at = {p.id: px(p.lon, p.lat) for p in spec.places}
    wid = width_of(spec)
    broken = {b for d in spec.disruptions for b in d.breaks}
    alt = {r for d in spec.disruptions for r in d.reroutes}
    body = [f'<clipPath id="c"><rect width="{W}" height="{height}"/></clipPath><g clip-path="url(#c)">', land(spec.bounds, px)]
    labels = []
    for f in spec.flows:
        stops = [at[i] for i in (f.source, *f.via, f.target) if i in at]
        cut = f.id in broken
        col = "#c8321e" if cut else "#2f6f9f" if f.id not in alt else "#3d7a4a"
        for a, b in zip(stops, stops[1:]):
            d, mid = _arc(a, b)
            body.append(f'<path d="{d}" fill="none" stroke="{col}" stroke-width="{wid[f.id]:g}" stroke-linecap="round" stroke-opacity="0.8"'
                        + (' stroke-dasharray="7 5"' if cut or f.id in alt else "") + "/>")
        if stops[-2:]:
            body.append(_arrow(*stops[-2], *stops[-1], col, 8 + wid[f.id] / 2))
        labels.append((f.commodity, mid, col))
    for p in spec.places:
        x, y = at[p.id]
        body.append(f'<circle cx="{x:.1f}" cy="{y:.1f}" r="{6 if p.role == "chokepoint" else 5}" fill="{INK}" stroke="#fff" stroke-width="1.5"/>')
        body.append(text_el(x + 8, y - 7, p.name, 11, INK, "700").replace("<text", '<text stroke="#f4f1ea" stroke-width="3" paint-order="stroke"', 1))
    for name, (x, y), col in labels:
        body.append(text_el(x, y - 4, name, 10, col, "700", "middle").replace("<text", '<text stroke="#f4f1ea" stroke-width="3" paint-order="stroke"', 1))
    body.append("</g>")
    cap = textwrap.wrap(spec.caption, 90)[:2]
    foot = "".join(text_el(18, height + 22 + 16 * j, line, 12, MUTED) for j, line in enumerate(cap))
    return svg_doc(W, height + 28 + 16 * len(cap), "".join(body) + foot, f"Flows: {spec.title}")


def tracker_compare_svg(spec: TrackerCompare) -> str:
    """Every line indexed to 100 where all of them have begun, on one time axis, labelled at its end."""
    cs = common_start(spec)
    rows = []
    for ln in spec.series:
        pts = [(d, v) for d, v in zip(ln.dates, ln.values) if d >= cs]
        base = pts[0][1] if pts else 0
        if len(pts) >= 2 and base:
            rows.append((ln, [(d, v / base * 100) for d, v in pts]))
    if not rows:
        return svg_doc(W, 60, text_el(18, 34, spec.title, 15, weight="700"), f"Trackers: {spec.title}")
    h, left, right, top, bottom = 340, 40, 170, 50, 40
    days = lambda d: date.fromisoformat(d).toordinal()    # noqa: E731
    x0, x1 = days(min(p[0][0] for _, p in rows)), days(max(p[-1][0] for _, p in rows))
    ys = [v for _, p in rows for _, v in p]
    lo, hi = min(ys + [100]), max(ys + [100])
    pad = (hi - lo) * 0.08 or 1
    lo, hi = lo - pad, hi + pad
    X = lambda d: left + (days(d) - x0) / max(x1 - x0, 1) * (W - left - right)       # noqa: E731
    Y = lambda v: top + (hi - v) / (hi - lo) * (h - top - bottom)                      # noqa: E731
    body = [text_el(18, 26, spec.title, 17, weight="700"),
            f'<line x1="{left}" y1="{Y(100):.1f}" x2="{W - right}" y2="{Y(100):.1f}" stroke="{RULE}" stroke-dasharray="4 4"/>',
            text_el(left - 6, Y(100) + 4, "100", 11, MUTED, anchor="end"),
            text_el(left, h - 18, rows[0][1][0][0], 11, MUTED), text_el(W - right, h - 18, max(p[-1][0] for _, p in rows), 11, MUTED, anchor="end")]
    for m in spec.markers:
        if cs <= m.date and left <= X(m.date) <= W - right:
            body.append(f'<line x1="{X(m.date):.1f}" y1="{top}" x2="{X(m.date):.1f}" y2="{h - bottom}" stroke="{RULE}"/>')
    for i, (ln, pts) in enumerate(rows):
        col = LINE_COLORS[i % len(LINE_COLORS)]
        body.append(f'<polyline points="{" ".join("%.1f,%.1f" % (X(d), Y(v)) for d, v in pts)}" fill="none" stroke="{col}" stroke-width="2.2" stroke-linejoin="round"/>')
        ex, ey = X(pts[-1][0]), Y(pts[-1][1])
        body.append(f'<circle cx="{ex:.1f}" cy="{ey:.1f}" r="3.5" fill="{col}"/>')
        body.append(text_el(ex + 8, ey + 4, f"{ln.label} {pts[-1][1]:.0f}", 11, col, "700"))
    cap = textwrap.wrap(f"{spec.caption} Indexed to 100 where every line has begun.", 90)[:2]
    foot = "".join(text_el(18, h + 6 + 16 * j, line, 12, MUTED) for j, line in enumerate(cap))
    return svg_doc(W, h + 14 + 16 * len(cap), "".join(body) + foot, f"Trackers: {spec.title}")
