"""Build ``sites/ohmega-monster/public/geo/land-lite.json``: a tiny world coastline for the site's globe spinner.

Source: Natural Earth 110m admin-0 countries (public domain; see data/README.md). Internal borders are removed (an edge shared by two
country rings is a border, not a coast), the remaining edges are stitched into polylines and Douglas-Peucker simplified.

    python make_land_lite.py [countries.geojson] [out.json] [tolerance_deg]

Output: ``{"v":1,"credit":str,"lines":[[lon,lat,lon,lat,...], ...]}`` with coordinates rounded to 0.1 degree. Stdlib only.
"""

from __future__ import annotations

import json
import math
import sys
from collections import defaultdict
from pathlib import Path

HERE = Path(__file__).resolve().parent
DEFAULT_SRC = HERE.parent / "data" / "natural_earth" / "ne_110m_admin_0_countries.geojson"
DEFAULT_OUT = HERE.parents[1] / "sites" / "ohmega-monster" / "public" / "geo" / "land-lite.json"
Pt = tuple[float, float]


def rings(geo: dict) -> list[list[Pt]]:
    out = []
    for f in geo["features"]:
        g = f["geometry"]
        polys = [g["coordinates"]] if g["type"] == "Polygon" else g["coordinates"] if g["type"] == "MultiPolygon" else []
        for poly in polys:
            for ring in poly:                       # outer rings and holes (lakes) alike
                out.append([(round(x, 3), round(y, 3)) for x, y, *_ in ring])
    return out


def coast_edges(rs: list[list[Pt]]) -> list[tuple[Pt, Pt]]:
    count: dict[frozenset, int] = defaultdict(int)
    for r in rs:
        for a, b in zip(r, r[1:]):
            if a != b:
                count[frozenset((a, b))] += 1
    def seam(a: Pt, b: Pt) -> bool:             # the map's own cut (antimeridian, south pole line), not a coast
        return (abs(a[0]) == 180 and a[0] == b[0]) or (a[1] <= -89.9 and b[1] <= -89.9)

    seen, out = set(), []
    for r in rs:
        for a, b in zip(r, r[1:]):
            k = frozenset((a, b))
            if a != b and count[k] == 1 and k not in seen and not seam(a, b):
                seen.add(k)
                out.append((a, b))
    return out


def stitch(edges: list[tuple[Pt, Pt]]) -> list[list[Pt]]:
    adj: dict[Pt, list[Pt]] = defaultdict(list)
    for a, b in edges:
        adj[a].append(b)
        adj[b].append(a)
    used: set[frozenset] = set()
    lines = []
    starts = [p for p, n in adj.items() if len(n) != 2] + list(adj)      # open ends first, then anything left (closed loops)
    for s in starts:
        for n in adj[s]:
            if frozenset((s, n)) in used:
                continue
            line, prev, cur = [s], s, n
            used.add(frozenset((s, n)))
            while True:
                line.append(cur)
                nxt = [m for m in adj[cur] if frozenset((cur, m)) not in used]
                if len(adj[cur]) != 2 or not nxt:
                    break
                used.add(frozenset((cur, nxt[0])))
                prev, cur = cur, nxt[0]
            lines.append(line)
    return lines


def dp(pts: list[Pt], tol: float) -> list[Pt]:
    if len(pts) < 3:
        return pts
    (x1, y1), (x2, y2) = pts[0], pts[-1]
    dx, dy = x2 - x1, y2 - y1
    norm = math.hypot(dx, dy)
    best, at = -1.0, 0
    for i in range(1, len(pts) - 1):
        x, y = pts[i]
        d = abs(dy * (x - x1) - dx * (y - y1)) / norm if norm else math.hypot(x - x1, y - y1)
        if d > best:
            best, at = d, i
    if best <= tol:
        return [pts[0], pts[-1]]
    return dp(pts[: at + 1], tol)[:-1] + dp(pts[at:], tol)


def main(src: Path, out: Path, tol: float) -> None:
    geo = json.loads(src.read_text(encoding="utf-8"))
    lines = [dp(line, tol) for line in stitch(coast_edges(rings(geo)))]
    flat = []
    for line in lines:
        if len(line) < 2:
            continue
        flat.append([v for x, y in line for v in (round(x, 1), round(y, 1))])
    doc = {"v": 1, "credit": "Natural Earth (public domain)", "lines": flat}
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(doc, separators=(",", ":")), encoding="utf-8")
    print(f"{len(flat)} lines, {sum(len(l) // 2 for l in flat)} points, {out.stat().st_size} bytes -> {out}")


if __name__ == "__main__":
    a = sys.argv[1:]
    main(Path(a[0]) if a else DEFAULT_SRC, Path(a[1]) if len(a) > 1 else DEFAULT_OUT, float(a[2]) if len(a) > 2 else 0.6)
