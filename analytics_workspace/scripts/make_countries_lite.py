"""Build ``sites/ohmega-monster/public/geo/countries-lite.json``: country polygons for the site's interactive globe.

Source: Natural Earth 110m admin-0 countries (public domain; see data/README.md).

Simplification must not open gaps between neighbours, so it is done once per shared ARC (TopoJSON-style): every unique edge is
stitched into arcs that break at junctions (nodes with other than two edges), each arc is Douglas-Peucker simplified once, and the
vertices that survive are the only ones any country ring keeps. A border shared by two countries therefore stays identical on both.

    python make_countries_lite.py [countries.geojson] [out.json] [tolerance_deg]

Output (coordinates rounded to 0.1 degree)::

    {"v":1,"credit":str,
     "countries":[{"iso":"FR","name":"France","rings":[[lon,lat,lon,lat,...], ...]}, ...],   # outer rings, closed implicitly
     "borders":[[lon,lat,...], ...],     # edges shared by two countries, stitched
     "coast":[[lon,lat,...], ...]}       # edges owned by one country, minus the map's own seams at lon +-180 and the south pole line

Stdlib only. ``iso`` is ISO_A2_EH (France, Norway and Kosovo have no plain ISO_A2 in Natural Earth); "" for the two unrecognised
territories (Northern Cyprus, Somaliland), which are drawn but never data-coloured.
"""

from __future__ import annotations

import json
import math
import sys
from collections import defaultdict
from pathlib import Path

from make_land_lite import dp, stitch

HERE = Path(__file__).resolve().parent
DEFAULT_SRC = HERE.parent / "data" / "natural_earth" / "ne_110m_admin_0_countries.geojson"
DEFAULT_OUT = HERE.parents[1] / "sites" / "ohmega-monster" / "public" / "geo" / "countries-lite.json"
Pt = tuple[float, float]
Edge = frozenset


def iso_of(props: dict) -> str:
    v = props.get("ISO_A2_EH") or props.get("ISO_A2") or ""
    return "" if v in ("-99", "-1") else v


def collect(geo: dict) -> list[tuple[str, str, list[list[Pt]]]]:
    """(iso, name, outer rings) per country; holes (enclaves such as Lesotho are separate features) are ignored."""
    out = []
    for f in geo["features"]:
        g = f["geometry"]
        polys = [g["coordinates"]] if g["type"] == "Polygon" else g["coordinates"] if g["type"] == "MultiPolygon" else []
        rings = [[(round(x, 3), round(y, 3)) for x, y, *_ in poly[0]] for poly in polys]
        out.append((iso_of(f["properties"]), f["properties"].get("NAME", ""), rings))
    return out


def is_seam(a: Pt, b: Pt) -> bool:
    return (abs(a[0]) == 180 and a[0] == b[0]) or (a[1] <= -89.9 and b[1] <= -89.9)


def main(src: Path, out: Path, tol: float) -> None:
    countries = collect(json.loads(src.read_text(encoding="utf-8")))
    count: dict[Edge, int] = defaultdict(int)
    for _, _, rings in countries:
        for r in rings:
            for a, b in zip(r, r[1:]):
                if a != b:
                    count[frozenset((a, b))] += 1

    edges = [tuple(e) for e in count]                       # every unique edge, seams included (rings need them)
    arcs = stitch(edges)
    kept: set[Pt] = set()
    simplified: list[tuple[list[Pt], int]] = []
    for arc in arcs:
        s = dp(arc, tol)
        kept.update(s)
        n = count[frozenset((arc[0], arc[1]))]              # an arc is homogeneous: all its edges share one count
        simplified.append((s, n))

    def pack(pts: list[Pt]) -> list[float]:
        return [v for x, y in pts for v in (round(x, 1), round(y, 1))]

    doc_countries = []
    for iso, name, rings in countries:
        outs = []
        for r in rings:
            pts = [p for p in r[:-1] if p in kept]          # drop the repeated closing vertex, then unsimplified vertices
            flat: list[Pt] = []
            for x, y in pts:
                q = (round(x, 1), round(y, 1))
                if not flat or flat[-1] != q:
                    flat.append(q)
            if len(flat) > 1 and flat[0] == flat[-1]:
                flat.pop()
            if len(flat) >= 3:
                outs.append(pack(flat))
        if outs:
            doc_countries.append({"iso": iso, "name": name, "rings": outs})

    borders = [pack(s) for s, n in simplified if n >= 2 and len(s) >= 2]
    coast = []
    for s, n in simplified:
        if n != 1:
            continue
        run: list[Pt] = []
        for a, b in zip(s, s[1:]):                           # cut seams out of the coast strokes
            if is_seam(a, b):
                if len(run) > 1:
                    coast.append(pack(run))
                run = []
                continue
            if not run:
                run = [a]
            run.append(b)
        if len(run) > 1:
            coast.append(pack(run))

    doc = {"v": 1, "credit": "Natural Earth (public domain)", "countries": doc_countries, "borders": borders, "coast": coast}
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(doc, separators=(",", ":"), ensure_ascii=False), encoding="utf-8")
    pts = sum(len(r) // 2 for c in doc_countries for r in c["rings"])
    print(f"{len(doc_countries)} countries, {pts} ring points, {len(borders)} border arcs, {len(coast)} coast arcs, {out.stat().st_size} bytes -> {out}")


if __name__ == "__main__":
    a = sys.argv[1:]
    main(Path(a[0]) if a else DEFAULT_SRC, Path(a[1]) if len(a) > 1 else DEFAULT_OUT, float(a[2]) if len(a) > 2 else 0.25)
