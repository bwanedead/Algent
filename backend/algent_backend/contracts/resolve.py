"""
From a document path to its contract, and the stamp a published document carries. The declarations live in the product registry
(``ops/products/registry.py``: ``Product.contracts``); this module only reads them, lazily, so importing ``contracts`` costs nothing.

* ``find(path)`` - the ``(product id, Contract)`` covering a logical document path. ``docs/`` prefixes and ``.gz`` suffixes do not matter. When several
  patterns match, the most specific wins (fewest wildcard segments, then the longest pattern): ``theaters/index.json`` beats ``theaters/*.json``.
* ``stamp_for(path, body)`` - the ``"<id>/<major>"`` string to put in a dict document that has none yet (``""`` when no contract applies).
* ``site_table()`` - the part of the registry the site needs, written to ``sites/ohmega-monster/lib/contracts.json`` (a test keeps it equal).
"""

from __future__ import annotations

import re
from functools import lru_cache
from typing import Any

#: Bump when the shape of ``site_table()`` changes.
TABLE_SCHEMA = "ohmega.contracts/1"


def _pattern(glob: str) -> re.Pattern[str]:
    out = ""
    for i, seg in enumerate(re.split(r"(\*\*|\*)", glob)):
        out += ".+" if seg == "**" else "[^/]+" if seg == "*" else re.escape(seg)
    return re.compile(f"^{out}$")


def normal(path: str) -> str:
    """A logical document path: no leading slash, no ``docs/`` prefix, no ``.gz``."""
    p = path.lstrip("/").removesuffix(".gz")
    return p.removeprefix("docs/") if p.startswith("docs/") else p


@lru_cache(maxsize=1)
def _table() -> list[tuple[re.Pattern[str], tuple[int, int], str, Any]]:
    from algent_backend.ops.products import views

    rows = []
    for p in views.products():
        for c in p.contracts:
            for glob in c.paths:
                rows.append((_pattern(glob), (glob.count("*"), -len(glob)), p.id, c))
    return rows


def contracts() -> list[tuple[str, Any]]:
    """Every ``(product id, Contract)`` in the registry."""
    from algent_backend.ops.products import views

    return [(p.id, c) for p in views.products() for c in p.contracts]


def find(path: str) -> tuple[str, Any] | None:
    p = normal(path)
    best = None
    for rx, rank, pid, c in _table():
        if rx.match(p) and (best is None or rank < best[0]):
            best = (rank, pid, c)
    return (best[1], best[2]) if best else None


def stamp_for(path: str, body: Any) -> str:
    """The schema stamp ``body`` should carry: ``""`` when no contract covers ``path``, ``body`` is not an object or it already has a ``schema``."""
    if not isinstance(body, dict) or "schema" in body:
        return ""
    hit = find(path)
    return hit[1].stamp if hit else ""


def parse_stamp(stamp: str) -> tuple[str, int] | None:
    """``"ohmega.daily/1"`` -> ``("ohmega.daily", 1)``; None for anything else."""
    m = re.fullmatch(r"(ohmega\.[\w.-]+)/(\d+)", stamp or "")
    return (m.group(1), int(m.group(2))) if m else None


def view_schema(family: str) -> str:
    """The stamp of a view family (``ohmega.view.country/1``): views/ builders take it from here so the registry is the only place that holds the number."""
    for _pid, c in contracts():
        if c.schema == f"ohmega.view.{family}":
            return c.stamp
    raise KeyError(f"no contract for view family {family!r}")


def site_table() -> dict[str, Any]:
    """What the site's parsers need: per schema its current major, the older majors still read, and the path patterns it covers."""
    rows = [{"schema": c.schema, "version": c.version, "accepts": sorted({c.version, *c.accepts}), "paths": list(c.paths), "product": pid} for pid, c in contracts()]
    return {"schema": TABLE_SCHEMA, "contracts": rows}
