"""
The graph around an entity: typed edges with their evidence (``edges``), and what it is most connected to (``related``), which also counts
documents, claims and events it shares with other entities, so a link nobody typed still shows up.
"""

from __future__ import annotations

import sqlite3
from typing import Any

_EDGE_WEIGHT, _CLAIM_WEIGHT, _EVENT_WEIGHT, _DOC_WEIGHT = 3.0, 2.0, 1.5, 1.0


def edges(db: sqlite3.Connection, entity_id: str, *, limit: int = 20) -> list[dict[str, Any]]:
    """Typed relations the entity is part of, grouped by (relation, direction, other end): how often, since when, and one piece of evidence."""
    out = []
    for r in db.execute(
            "SELECT r.rel, 'out' AS dir, r.dst_id AS other, COUNT(*) AS n, MAX(r.date) AS latest, MIN(r.date) AS earliest, "
            "MAX(r.document_id) AS evidence, MAX(r.note) AS note FROM relations r WHERE r.src_id = ?1 AND r.dst_id IS NOT NULL GROUP BY r.rel, r.dst_id "
            "UNION ALL SELECT r.rel, 'in', r.src_id, COUNT(*), MAX(r.date), MIN(r.date), MAX(r.document_id), MAX(r.note) FROM relations r "
            "WHERE r.dst_id = ?1 AND r.src_id IS NOT NULL GROUP BY r.rel, r.src_id ORDER BY n DESC, latest DESC LIMIT ?2", (entity_id, limit)):
        e = db.execute("SELECT name, kind FROM entities WHERE id = ?", (r["other"],)).fetchone()
        out.append({"rel": r["rel"], "direction": r["dir"], "entity": r["other"], "name": e["name"] if e else r["other"], "kind": e["kind"] if e else "",
                    "count": r["n"], "latest": r["latest"], "earliest": r["earliest"], "evidence": r["evidence"], "note": r["note"]})
    return out


def related(db: sqlite3.Connection, entity_id: str, *, limit: int = 15, kinds: set[str] | None = None) -> list[dict[str, Any]]:
    """Entities most connected to this one. Score = typed edges x3 + shared claims x2 + shared events x1.5 + shared documents x1; ``via`` shows the parts."""
    score: dict[str, dict[str, float]] = {}

    def add(rows, key: str) -> None:
        for r in rows:
            if r[0] and r[0] != entity_id:
                score.setdefault(r[0], {}).setdefault(key, 0.0)
                score[r[0]][key] += r[1]

    add(db.execute("SELECT dst_id, COUNT(*) FROM relations WHERE src_id = ? AND dst_id IS NOT NULL GROUP BY dst_id", (entity_id,)), "edges")
    add(db.execute("SELECT src_id, COUNT(*) FROM relations WHERE dst_id = ? AND src_id IS NOT NULL GROUP BY src_id", (entity_id,)), "edges")
    add(db.execute("SELECT m2.entity_id, COUNT(DISTINCT m1.claim_id) FROM mentions m1 JOIN mentions m2 ON m2.claim_id = m1.claim_id AND m2.entity_id != m1.entity_id "
                   "WHERE m1.entity_id = ? AND m1.claim_id != '' AND m2.entity_id IS NOT NULL GROUP BY m2.entity_id", (entity_id,)), "claims")
    add(db.execute("SELECT m2.entity_id, COUNT(DISTINCT m1.document_id) FROM mentions m1 JOIN mentions m2 ON m2.document_id = m1.document_id AND m2.entity_id != m1.entity_id "
                   "WHERE m1.entity_id = ? AND m1.document_id != '' AND m2.entity_id IS NOT NULL GROUP BY m2.entity_id", (entity_id,)), "documents")
    add(db.execute("SELECT a2.entity_id, COUNT(DISTINCT a1.event_id) FROM event_actors a1 JOIN event_actors a2 ON a2.event_id = a1.event_id AND a2.entity_id != a1.entity_id "
                   "WHERE a1.entity_id = ? AND a2.entity_id IS NOT NULL GROUP BY a2.entity_id", (entity_id,)), "events")
    weights = {"edges": _EDGE_WEIGHT, "claims": _CLAIM_WEIGHT, "events": _EVENT_WEIGHT, "documents": _DOC_WEIGHT}
    ranked = sorted(score.items(), key=lambda kv: (-sum(weights[k] * v for k, v in kv[1].items()), kv[0]))
    out = []
    for other, via in ranked:
        e = db.execute("SELECT id, name, kind FROM entities WHERE id = ?", (other,)).fetchone()
        if e is None or (kinds and e["kind"] not in kinds):
            continue
        out.append({"entity": e["id"], "name": e["name"], "kind": e["kind"], "score": round(sum(weights[k] * v for k, v in via.items()), 1),
                    "via": {k: int(v) for k, v in via.items()}})
        if len(out) >= limit:
            break
    return out
