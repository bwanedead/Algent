"""
Live tiles — the bandwidth-friendly form of the vessel and aircraft snapshots.

One full ``vessels.json.gz`` is ~0.8 MB (60,000 ships) and an open tab pulled it every minute. The site now pulls:

* ``density`` — a world grid of ``DENSITY_DEG`` degree cells with counts per class, per layer (a few KB gzipped). All a world-zoom
  view needs: it draws density, not objects.
* ``tiles/index`` — which ``TILE_DEG`` degree tiles exist per layer, with object counts and an etag (a short content hash).
* ``tiles/v/<tile>`` and ``tiles/a/<tile>`` — the object rows (same row layout as the full documents) of one tile, only for
  non-empty tiles. The site fetches just the tiles under the viewport and refetches one only when its etag changed. A tile carries
  no timestamp of its own (the index has ``as_of``), so a tile whose rows did not change hashes the same and is not re-uploaded.

Cell and tile ids are row-major from the south-west corner: ``id = row * cols + col`` for a density cell (``row = floor((lat + 90) /
deg)``, ``col = floor((lon + 180) / deg)``, ``cols = 360 / deg`` — the same convention as the coverage grid), and ``r<row>c<col>``
(two digits each) for a tile. Pure functions of the two board documents; nothing here touches the network.
"""

from __future__ import annotations

import hashlib
from typing import Any

from . import flags
from .snapshots import encode

LAYERS = (("vessels", "v"), ("aircraft", "a"))     # (document name, tile folder)
_LON, _LAT, _CLS = 1, 2, 5                          # row positions shared by both documents


def _cell(lat: float, lon: float, deg: int) -> tuple[int, int]:
    rows, cols = 180 // deg, 360 // deg
    return min(rows - 1, max(0, int((lat + 90) // deg))), min(cols - 1, max(0, int((lon + 180) // deg)))


def cell_id(lat: float, lon: float, deg: int) -> int:
    row, col = _cell(lat, lon, deg)
    return row * (360 // deg) + col


def tile_id(lat: float, lon: float, deg: int | None = None) -> str:
    row, col = _cell(lat, lon, deg or flags.TILE_DEG)
    return f"r{row:02d}c{col:02d}"


def density(doc: dict[str, Any], deg: int | None = None) -> dict[str, Any]:
    """One layer's grid: ``{"n", "counts", "classes", "cells": [[id, n_class0, n_class1, ...], ...]}`` (trailing zero counts dropped)."""
    deg = deg or flags.DENSITY_DEG
    grid: dict[int, list[int]] = {}
    width = len(doc.get("classes", ())) or 6
    for r in doc["rows"]:
        cell = grid.setdefault(cell_id(r[_LAT], r[_LON], deg), [0] * width)
        cell[min(int(r[_CLS]), width - 1)] += 1
    cells = []
    for cid in sorted(grid):
        counts = grid[cid]
        while counts and not counts[-1]:
            counts.pop()
        cells.append([cid, *counts])
    return {"n": doc["n"], "counts": doc.get("counts", {}), "classes": doc.get("classes", []), "cells": cells}


def split(doc: dict[str, Any], deg: int | None = None) -> dict[str, dict[str, Any]]:
    """``{tile id: {"v": 1, "tile", "n", "f", "rows"}}`` for the non-empty tiles of one layer's full document."""
    deg = deg or flags.TILE_DEG
    by: dict[str, list] = {}
    for r in doc["rows"]:
        by.setdefault(tile_id(r[_LAT], r[_LON], deg), []).append(r)
    return {tid: {"v": 1, "tile": tid, "n": len(rows), "f": doc.get("f", []), "rows": rows} for tid, rows in sorted(by.items())}


def etag(tile: dict[str, Any]) -> str:
    return hashlib.sha1(encode(tile)).hexdigest()[:10]


def build(vessels: dict[str, Any], aircraft: dict[str, Any]) -> dict[str, Any]:
    """The documents of one cycle, named for ``snapshots.publish``: ``density``, ``tiles/index`` and ``tiles/<v|a>/<tile>``."""
    src = {"vessels": vessels, "aircraft": aircraft}
    out: dict[str, Any] = {}
    index: dict[str, Any] = {"v": 1, "as_of": vessels["as_of"], "aircraft_as_of": aircraft["as_of"], "deg": flags.TILE_DEG}
    for name, folder in LAYERS:
        listing = {}
        for tid, tile in split(src[name]).items():
            out[f"tiles/{folder}/{tid}"] = tile
            listing[tid] = [tile["n"], etag(tile)]
        index[name] = listing
    out["tiles/index"] = index
    out["density"] = {"v": 1, "as_of": vessels["as_of"], "aircraft_as_of": aircraft["as_of"], "deg": flags.DENSITY_DEG,
                      "layers": {name: density(src[name]) for name, _ in LAYERS}}
    return out
