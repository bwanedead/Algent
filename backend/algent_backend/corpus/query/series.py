"""Time series: every observation of an entity (any metric) or of a metric (any entity), grouped into series that each state their basis and unit."""

from __future__ import annotations

import sqlite3
from typing import Any


def series(db: sqlite3.Connection, *, entity_id: str = "", metric: str = "", since: str = "", until: str = "", points: bool = True,
           limit: int = 40) -> list[dict[str, Any]]:
    """Series for an entity, a metric, or both. ``metric`` matches exactly, or as a prefix when it ends with ``.`` or ``*`` (``bench.``, ``pulse.*``)."""
    where, args = ["ts >= ?"], [since]
    if entity_id:
        where.append("entity_id = ?")
        args.append(entity_id)
    if metric:
        if metric.endswith(("*", ".")):
            where.append("metric LIKE ?")
            args.append(metric.rstrip("*") + "%")
        else:
            where.append("metric = ?")
            args.append(metric)
    if until:
        where.append("ts <= ?")
        args.append(until)
    groups = db.execute(
        f"SELECT entity_id, metric, COUNT(*) AS n, MIN(ts) AS first, MAX(ts) AS last, MAX(unit) AS unit, MAX(basis) AS basis, MAX(label) AS label, "      # noqa: S608
        f"MAX(product) AS product FROM observations WHERE {' AND '.join(where)} GROUP BY entity_id, metric ORDER BY last DESC, n DESC, metric LIMIT ?",
        [*args, limit]).fetchall()
    out = []
    for g in groups:
        name = ""
        if g["entity_id"]:
            e = db.execute("SELECT name FROM entities WHERE id = ?", (g["entity_id"],)).fetchone()
            name = e["name"] if e else g["entity_id"]
        s = {"metric": g["metric"], "entity": g["entity_id"], "entity_name": name, "label": g["label"], "unit": g["unit"], "basis": g["basis"],
             "n": g["n"], "first": g["first"], "last": g["last"], "product": g["product"]}
        if points:
            rows = db.execute("SELECT ts, value, source_url FROM observations WHERE entity_id = ? AND metric = ? AND ts >= ? ORDER BY ts",
                              (g["entity_id"], g["metric"], since)).fetchall()
            s["points"] = [[r["ts"], r["value"]] for r in rows]
            s["latest"] = {"ts": rows[-1]["ts"], "value": rows[-1]["value"], "source": rows[-1]["source_url"]} if rows else None
        out.append(s)
    return out
