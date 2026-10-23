"""
The slice of the index retrieval needs: documents of chosen kinds inside per-kind date windows (so a replay sees only what was known then), with
the ranking done by the index's own full-text search. Plain dicts only: this package does not know the retrieval package's types.
"""

from __future__ import annotations

import sqlite3
from dataclasses import dataclass
from typing import Any

from .search import document_ranking


@dataclass(frozen=True)
class Window:
    kind: str                       # documents.kind
    lo: str                         # earliest date, inclusive
    hi: str                         # latest date, inclusive
    domain: str = ""                # only this desk (documents.domain), when set
    status: str = ""                # only this status, when set
    not_status: str = ""            # never this status, when set


def window_docs(db: sqlite3.Connection, windows: list[Window]) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for w in windows:
        sql = "SELECT id, kind, date, title, body AS text FROM documents WHERE kind = ? AND date >= ? AND date <= ?"
        args: list[Any] = [w.kind, w.lo, w.hi]
        for col, val, op in (("domain", w.domain, "="), ("status", w.status, "="), ("status", w.not_status, "!=")):
            if val:
                sql, args = f"{sql} AND {col} {op} ?", [*args, val]
        out += [dict(r) for r in db.execute(sql + " ORDER BY date, id", args)]
    return out


def rank(db: sqlite3.Connection, text: str, *, limit: int = 400) -> list[str]:
    """Document ids best first for the text (all documents, not only the window: the caller keeps the ids it loaded)."""
    return document_ranking(db, text, limit=limit)
