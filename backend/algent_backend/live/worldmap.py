"""
World basemap for the site's /live page — one simplified plate-carree spec from the desk's Natural Earth countries.

    {"bbox":[w,s,e,n], "width":1000, "height":int, "countries":[{"name","d"}], "credit":str}

The page projects live events itself (x = (lon - w) * width / (e - w), y = (n - lat) * height / (n - s)). Published as the
document ``live/world.json`` (idempotent: an unchanged map is not rewritten). Antarctica is cropped by the frame.
"""

from __future__ import annotations

from typing import Any

from . import places

WIDTH = 1000
FRAME = (-180.0, -58.0, 180.0, 84.0)       # w, s, e, n
TOLERANCE = 0.8                            # frame units: coarse on purpose, this is a locator for dots, not an atlas
CREDIT = "Base map: Natural Earth (public domain). Data: IODA, USGS, adsb.lol, NASA FIRMS, aisstream.io; positions approximate."


def build() -> dict[str, Any] | None:
    from algent_backend.agent_system.agents.intel.geo_draw import clip_ring, ring_path

    countries = places._countries()
    if not countries:
        return None
    w, s, e, n = FRAME
    sx = WIDTH / (e - w)
    height = round((n - s) * sx)
    box = (0.0, 0.0, float(WIDTH), float(height))
    out = []
    for c in countries:
        rings = []
        for poly in c.polygons:
            if not poly:
                continue
            ring = clip_ring([((x - w) * sx, (n - y) * sx) for x, y in poly[0]], box)
            if ring:
                rings.append(ring)
        if d := ring_path(rings, TOLERANCE):
            out.append({"name": c.name, "d": d})
    return {"bbox": [w, s, e, n], "width": WIDTH, "height": height, "countries": out, "credit": CREDIT}
