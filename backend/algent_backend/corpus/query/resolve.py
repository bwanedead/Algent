"""Finding an entity from what a person or an agent typed: an exact id, else a name or alias, most-mentioned first. Never silently picks between two: callers get all candidates."""

from __future__ import annotations

import json
import sqlite3
from typing import Any

from ..norm import norm

_CANDIDATES = (
    "SELECT e.*, (SELECT COUNT(*) FROM mentions m WHERE m.entity_id = e.id) AS uses FROM entities e "
    "JOIN entity_alias a ON a.entity_id = e.id WHERE {where} GROUP BY e.id ORDER BY uses DESC, e.id LIMIT 20")


def shape(row: sqlite3.Row | dict) -> dict[str, Any]:
    d = dict(row)
    d["aliases"] = json.loads(d.get("aliases") or "[]")
    d["attrs"] = json.loads(d.get("attrs") or "{}")
    d.pop("uses", None)
    return d


def find(db: sqlite3.Connection, ref: str, *, kinds: set[str] | None = None) -> list[dict[str, Any]]:
    """Candidates for ``ref``, best first: the entity with that id; else those answering to that name exactly; else those whose name contains it."""
    ref = (ref or "").strip()
    if not ref:
        return []
    row = db.execute("SELECT * FROM entities WHERE id = ?", (ref,)).fetchone()
    found = [shape(row)] if row else []
    if not found:
        n = norm(ref)
        for where, arg in (("a.norm = ?", n), ("a.norm LIKE ?", f"%{n}%")):
            found = [shape(r) for r in db.execute(_CANDIDATES.format(where=where), (arg,))]
            if found:
                break
    return [e for e in found if not kinds or e["kind"] in kinds]


def get(db: sqlite3.Connection, ref: str) -> tuple[dict[str, Any] | None, list[dict[str, Any]]]:
    """(the best candidate, the other candidates). The others are returned so the caller can say the name was ambiguous."""
    found = find(db, ref)
    return (found[0], found[1:]) if found else (None, [])
