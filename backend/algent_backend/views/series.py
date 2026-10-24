"""
``views/series/<metric>.json`` and ``views/series-index.json``: a measured series across the entities that have it (GDP of every state, a chokepoint's daily transits, a
benchmark's scores), each with its unit and its ``basis`` in the stats-registry vocabulary (official / our_count / our_derived / model / reported / ...). The index lists
every metric so an agent can find one by name or prefix. Per-entity series are in the entity views.
"""

from __future__ import annotations

import re
from typing import Any

from . import flags
from .base import View, make
from .context import ViewContext

_SAFE = re.compile(r"[^A-Za-z0-9._-]+")
SERIES_MIN_POINTS = 3


def metric_key(metric: str) -> str:
    """``series/<metric made path-safe>``; the site computes the same key for ids made of letters, digits, ``.``, ``_`` and ``-``."""
    return f"series/{_SAFE.sub('_', metric).strip('_') or 'x'}"


_METRICS = """
SELECT metric, COUNT(*) AS n, COUNT(DISTINCT entity_id) AS entities, MAX(unit) AS unit, MAX(basis) AS basis, MAX(label) AS label, MAX(product) AS product,
       MIN(ts) AS first, MAX(ts) AS last FROM observations GROUP BY metric HAVING COUNT(*) >= ? ORDER BY n DESC, metric LIMIT ?
"""


def build(ctx: ViewContext) -> list[View]:
    if ctx.corpus is None:
        return []
    db = ctx.corpus.db
    index, views = [], []
    for m in db.execute(_METRICS, (SERIES_MIN_POINTS, flags.SERIES_METRICS)).fetchall():
        who = db.execute("SELECT entity_id, COUNT(*) AS n, MIN(ts) AS first, MAX(ts) AS last FROM observations WHERE metric = ? GROUP BY entity_id ORDER BY last DESC, n DESC, entity_id LIMIT ?",
                         (m["metric"], flags.SERIES_ENTITIES)).fetchall()
        entities: list[dict[str, Any]] = []
        for w in who:
            name = ""
            if w["entity_id"]:
                e = db.execute("SELECT name FROM entities WHERE id = ?", (w["entity_id"],)).fetchone()
                name = e["name"] if e else w["entity_id"]
            pts = db.execute("SELECT ts, value, source_url FROM observations WHERE metric = ? AND entity_id = ? ORDER BY ts DESC LIMIT ?", (m["metric"], w["entity_id"], flags.SERIES_POINTS)).fetchall()[::-1]
            entities.append({"entity": w["entity_id"], "name": name, "n": w["n"], "first": w["first"], "last": w["last"], "points": [[p["ts"], p["value"]] for p in pts],
                             "latest": {"ts": pts[-1]["ts"], "value": pts[-1]["value"], "source": pts[-1]["source_url"]} if pts else None})
        key = metric_key(m["metric"])
        head = {"metric": m["metric"], "label": m["label"], "unit": m["unit"], "basis": m["basis"], "product": m["product"], "n": m["n"], "entities_total": m["entities"],
                "first": m["first"], "last": m["last"]}
        views.append(make("series", key, {**head, "key": key, "entities": entities}, as_of=str(m["last"] or "")[:10], sources=[("corpus_index", f"metric {m['metric']}")]))
        index.append({**head, "key": key})
    as_of = max((r["last"][:10] for r in index if r["last"]), default="")
    return [*views, make("series-index", "series-index", {"metrics": index, "metrics_total": len(index)}, as_of=as_of, sources=[("corpus_index", "observations")])]
