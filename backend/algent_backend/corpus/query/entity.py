"""The profile of one entity: who it is, what we last knew, which situations it sits in, what it is connected to, and its recent timeline."""

from __future__ import annotations

import sqlite3
from typing import Any

from . import about, graph, series


def _count(db: sqlite3.Connection, sql: str, *args: Any) -> int:
    return db.execute(sql, args).fetchone()[0]


def situations(db: sqlite3.Connection, entity_id: str, *, limit: int = 5) -> list[dict[str, Any]]:
    """Situations (theaters, Pulse situations) the entity shares documents, events or typed edges with, most shared first."""
    rows = db.execute(
        "SELECT e.id, e.name, SUM(n) AS shared FROM ("
        " SELECT m2.entity_id AS sid, COUNT(DISTINCT m1.document_id) AS n FROM mentions m1 JOIN mentions m2 ON m2.document_id = m1.document_id "
        "  WHERE m1.entity_id = ?1 AND m1.document_id != '' AND m2.entity_id IS NOT NULL GROUP BY m2.entity_id"
        " UNION ALL SELECT a2.entity_id, COUNT(DISTINCT a1.event_id) FROM event_actors a1 JOIN event_actors a2 ON a2.event_id = a1.event_id "
        "  WHERE a1.entity_id = ?1 AND a2.entity_id IS NOT NULL GROUP BY a2.entity_id"
        " UNION ALL SELECT dst_id, COUNT(*) FROM relations WHERE src_id = ?1 AND dst_id IS NOT NULL GROUP BY dst_id"
        " UNION ALL SELECT src_id, COUNT(*) FROM relations WHERE dst_id = ?1 AND src_id IS NOT NULL GROUP BY src_id) x "
        "JOIN entities e ON e.id = x.sid WHERE e.kind = 'situation' AND e.id != ?1 GROUP BY e.id ORDER BY shared DESC, e.id LIMIT ?2", (entity_id, limit))
    return [{"entity": r["id"], "name": r["name"], "shared": r["shared"]} for r in rows]


def latest(db: sqlite3.Connection, entity: dict[str, Any]) -> dict[str, Any]:
    """The newest thing we know: its last event and the last value of each of its series (a pulse's position, a market's price...)."""
    last_event = about.events(db, entity["id"], limit=1)
    obs = [{"metric": s["metric"], "label": s["label"], "ts": s["latest"]["ts"], "value": s["latest"]["value"], "unit": s["unit"], "basis": s["basis"]}
           for s in series.series(db, entity_id=entity["id"], limit=8) if s.get("latest")]
    out: dict[str, Any] = {"event": last_event[0] if last_event else None, "observations": obs}
    heads = [e for e in graph.edges(db, entity["id"], limit=50) if e["rel"] in ("head_of_state", "head_of_government") and e["direction"] == "out"]
    if heads:
        out["leaders"] = [{"office": e["rel"], "name": e["name"], "since": e["latest"]} for e in heads]
    return out


def profile(db: sqlite3.Connection, entity: dict[str, Any], *, timeline_n: int = 10) -> dict[str, Any]:
    eid = entity["id"]
    return {
        "entity": entity,
        "counts": {"documents": _count(db, "SELECT COUNT(DISTINCT document_id) FROM mentions WHERE entity_id = ? AND document_id != ''", eid),
                   "claims": _count(db, "SELECT COUNT(DISTINCT claim_id) FROM mentions WHERE entity_id = ? AND claim_id != ''", eid),
                   "events": _count(db, "SELECT COUNT(*) FROM events WHERE place_id = ?1 OR id IN (SELECT event_id FROM event_actors WHERE entity_id = ?1)", eid),
                   "series": _count(db, "SELECT COUNT(*) FROM (SELECT 1 FROM observations WHERE entity_id = ? GROUP BY metric)", eid)},
        "latest": latest(db, entity),
        "situations": situations(db, eid),
        "relations": graph.edges(db, eid, limit=12),
        "timeline": about.timeline(db, eid, limit=timeline_n),
    }
