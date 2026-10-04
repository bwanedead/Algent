"""
Pure drawing geometry for the daily maps: no I/O, no domain knowledge, no shapely.

Everything here works in the map's own frame (x right, y down, 0..width by 0..height) after projection:
Douglas-Peucker simplification, rectangle clipping of rings and lines, SVG path text, a visible-area
label anchor, and the scale bar. ``geo.build_map`` composes them.
"""

from __future__ import annotations

import math

Pt = tuple[float, float]
Box = tuple[float, float, float, float]          # x0, y0, x1, y1
EARTH_KM_PER_DEG = 111.32                         # one degree of longitude at the equator


def fmt(v: float, places: int = 1) -> str:
    return f"{v:.{places}f}".removesuffix(".0") if places else f"{v:.0f}"


# ── simplification ────────────────────────────────────────────────────────────────────────────
def _dp(pts: list[Pt], tol: float) -> list[Pt]:
    """Douglas-Peucker on an open polyline (iterative: a 50m coastline is thousands of vertices)."""
    if len(pts) < 3:
        return list(pts)
    keep = [False] * len(pts)
    keep[0] = keep[-1] = True
    stack = [(0, len(pts) - 1)]
    while stack:
        lo, hi = stack.pop()
        (ax, ay), (bx, by) = pts[lo], pts[hi]
        dx, dy = bx - ax, by - ay
        norm = math.hypot(dx, dy)
        far, far_d = -1, tol
        for i in range(lo + 1, hi):
            px, py = pts[i]
            d = math.hypot(px - ax, py - ay) if norm == 0 else abs(dx * (ay - py) - dy * (ax - px)) / norm
            if d > far_d:
                far, far_d = i, d
        if far >= 0:
            keep[far] = True
            stack += [(lo, far), (far, hi)]
    return [p for p, k in zip(pts, keep, strict=True) if k]


def simplify(pts: list[Pt], tol: float, closed: bool = False) -> list[Pt]:
    """Douglas-Peucker. A closed ring is split at the vertex farthest from its start so the seam is not
    privileged; the result stays closed (first vertex not repeated). ``tol`` is in frame units: the largest
    distance a dropped vertex may sit from the simplified line."""
    if not closed:
        return _dp(pts, tol)
    ring = pts[:-1] if len(pts) > 1 and pts[0] == pts[-1] else list(pts)
    if len(ring) < 4:
        return ring
    k = max(range(len(ring)), key=lambda i: math.hypot(ring[i][0] - ring[0][0], ring[i][1] - ring[0][1]))
    a, b = _dp(ring[: k + 1], tol), _dp(ring[k:] + [ring[0]], tol)
    return a[:-1] + b[:-1]


# ── clipping ──────────────────────────────────────────────────────────────────────────────────
def clip_ring(ring: list[Pt], box: Box) -> list[Pt]:
    """Sutherland-Hodgman against the frame rectangle."""
    x0, y0, x1, y1 = box
    edges = ((lambda p: p[0] >= x0, lambda a, b: (x0, a[1] + (b[1] - a[1]) * (x0 - a[0]) / (b[0] - a[0]))),
             (lambda p: p[0] <= x1, lambda a, b: (x1, a[1] + (b[1] - a[1]) * (x1 - a[0]) / (b[0] - a[0]))),
             (lambda p: p[1] >= y0, lambda a, b: (a[0] + (b[0] - a[0]) * (y0 - a[1]) / (b[1] - a[1]), y0)),
             (lambda p: p[1] <= y1, lambda a, b: (a[0] + (b[0] - a[0]) * (y1 - a[1]) / (b[1] - a[1]), y1)))
    for inside, cut in edges:
        src, ring = ring, []
        for i, cur in enumerate(src):
            prev = src[i - 1]
            if inside(cur):
                if not inside(prev):
                    ring.append(cut(prev, cur))
                ring.append(cur)
            elif inside(prev):
                ring.append(cut(prev, cur))
        if not ring:
            return []
    return ring


def _clip_segment(a: Pt, b: Pt, box: Box) -> tuple[Pt, Pt] | None:
    """Liang-Barsky: the part of segment ab inside the box, or None."""
    x0, y0, x1, y1 = box
    dx, dy = b[0] - a[0], b[1] - a[1]
    t0, t1 = 0.0, 1.0
    for p, q in ((-dx, a[0] - x0), (dx, x1 - a[0]), (-dy, a[1] - y0), (dy, y1 - a[1])):
        if p == 0:
            if q < 0:
                return None
            continue
        t = q / p
        if p < 0:
            t0 = max(t0, t)
        else:
            t1 = min(t1, t)
        if t0 > t1:
            return None
    return (a[0] + t0 * dx, a[1] + t0 * dy), (a[0] + t1 * dx, a[1] + t1 * dy)


def clip_line(line: list[Pt], box: Box) -> list[list[Pt]]:
    """A polyline cut to the box: zero or more connected pieces."""
    pieces: list[list[Pt]] = []
    cur: list[Pt] = []
    for a, b in zip(line, line[1:], strict=False):
        seg = _clip_segment(a, b, box)
        if seg is None:
            if len(cur) > 1:
                pieces.append(cur)
            cur = []
            continue
        if cur and cur[-1] == seg[0]:
            cur.append(seg[1])
        else:
            if len(cur) > 1:
                pieces.append(cur)
            cur = [seg[0], seg[1]]
    if len(cur) > 1:
        pieces.append(cur)
    return pieces


# ── paths and measures ────────────────────────────────────────────────────────────────────────
def ring_area(ring: list[Pt]) -> float:
    """Absolute shoelace area."""
    return abs(sum(x1 * y2 - x2 * y1 for (x1, y1), (x2, y2) in zip(ring, ring[1:] + ring[:1], strict=True))) / 2


def extent(pts: list[Pt]) -> float:
    xs, ys = [p[0] for p in pts], [p[1] for p in pts]
    return max(max(xs) - min(xs), max(ys) - min(ys))


def ring_path(rings: list[list[Pt]], tol: float, min_extent: float = 1.5, places: int = 1) -> str:
    """SVG path text for closed rings, simplified to ``tol``; specks smaller than ``min_extent`` are dropped."""
    parts = []
    for ring in rings:
        if len(ring) < 3 or extent(ring) < min_extent:
            continue
        kept = simplify(ring, tol, closed=True)
        if len(kept) >= 3:
            parts.append("M" + "L".join(f"{fmt(x, places)} {fmt(y, places)}" for x, y in kept) + "Z")
    return "".join(parts)


def line_path(lines: list[list[Pt]], tol: float, min_extent: float = 4.0) -> str:
    parts = []
    for line in lines:
        if len(line) < 2 or extent(line) < min_extent:
            continue
        kept = simplify(line, tol)
        if len(kept) >= 2:
            parts.append("M" + "L".join(f"{fmt(x)} {fmt(y)}" for x, y in kept))
    return "".join(parts)


def _in_ring(x: float, y: float, ring: list[Pt]) -> bool:
    inside, j = False, len(ring) - 1
    for i, (xi, yi) in enumerate(ring):
        xj, yj = ring[j]
        if (yi > y) != (yj > y) and x < (xj - xi) * (y - yi) / (yj - yi) + xi:
            inside = not inside
        j = i
    return inside


def _edge_dist(x: float, y: float, rings: list[list[Pt]]) -> float:
    best = math.inf
    for ring in rings:
        for (x1, y1), (x2, y2) in zip(ring, ring[1:] + ring[:1], strict=True):
            dx, dy = x2 - x1, y2 - y1
            t = 0.0 if dx == dy == 0 else max(0.0, min(1.0, ((x - x1) * dx + (y - y1) * dy) / (dx * dx + dy * dy)))
            best = min(best, math.hypot(x1 + t * dx - x, y1 + t * dy - y))
    return best


def anchor(outer: list[Pt], holes: list[list[Pt]] | None = None) -> tuple[float, float, float]:
    """(x, y, r): a point well inside the polygon and the radius of the largest circle there that stays inside
    (a coarse pole of inaccessibility: a grid search, then one refinement). Used to seat a country's name."""
    rings = [outer, *(holes or [])]
    xs, ys = [p[0] for p in outer], [p[1] for p in outer]
    best = (sum(xs) / len(xs), sum(ys) / len(ys), 0.0)

    def inside(x: float, y: float) -> bool:
        return _in_ring(x, y, outer) and not any(_in_ring(x, y, h) for h in (holes or []))

    def search(x0: float, y0: float, x1: float, y1: float, n: int) -> None:
        nonlocal best
        for i in range(n + 1):
            for j in range(n + 1):
                x, y = x0 + (x1 - x0) * i / n, y0 + (y1 - y0) * j / n
                if inside(x, y):
                    d = _edge_dist(x, y, rings)
                    if d > best[2]:
                        best = (x, y, d)

    search(min(xs), min(ys), max(xs), max(ys), 14)
    if best[2] > 0:
        step = max(max(xs) - min(xs), max(ys) - min(ys)) / 14
        search(best[0] - step, best[1] - step, best[0] + step, best[1] + step, 8)
    return best


# ── scale bar ─────────────────────────────────────────────────────────────────────────────────
def km_per_unit(west: float, east: float, mid_lat: float, width: float) -> float:
    """Ground distance of one frame unit along the horizontal at ``mid_lat`` (the projection is exact there)."""
    return (east - west) * EARTH_KM_PER_DEG * math.cos(math.radians(mid_lat)) / width


def nice_km(limit: float) -> float:
    """The largest 1-2-5 x 10^k that is <= limit (a round distance a reader can use)."""
    if limit <= 0:
        return 1.0
    mag = 10 ** math.floor(math.log10(limit))
    return next(m * mag for m in (5, 2, 1) if m * mag <= limit)


def scale_bar(west: float, east: float, mid_lat: float, width: float, share: float = 0.2) -> dict:
    """A bar of a round number of km no longer than ``share`` of the frame width: {km, px, label}."""
    per_unit = km_per_unit(west, east, mid_lat, width)
    km = nice_km(width * share * per_unit)
    return {"km": km, "px": round(km / per_unit, 1), "label": f"{km:,.0f} km"}
