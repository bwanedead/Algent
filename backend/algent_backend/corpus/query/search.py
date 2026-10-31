"""
Full-text search over document titles and bodies, claims and events. FTS5 (porter stemming, BM25 with titles weighted double) when the index was
built with it; else a LIKE scan ranked by how many query terms hit. Either way a hit names the thing it found (kind + id), a snippet and a date.
"""

from __future__ import annotations

import re
import sqlite3
from typing import Any

from .. import flags
from ..norm import norm

_OVERFETCH = 8                                  # candidates pulled per wanted hit, so kind/date filters applied afterwards still fill the page
_PRODUCT_POOL = 400                             # candidates pulled when the page is restricted to a product (the FTS table does not index the product)


def terms(text: str) -> list[str]:
    seen: dict[str, None] = {}
    for t in re.findall(r"[a-z0-9]{2,}", norm(text)):
        seen.setdefault(t)
    return list(seen)[: flags.QUERY_TERMS_MAX]


def _candidates(db: sqlite3.Connection, ts: list[str], fts: bool, n: int, only: str = "") -> list[sqlite3.Row]:
    if fts:
        q = " OR ".join(f'"{t}"' for t in ts)
        return db.execute("SELECT kind, ref, bm25(search, 4.0, 1.0) AS score, snippet(search, 1, '[', ']', '…', 14) AS snip FROM search "
                          "WHERE search MATCH ? AND (? = '' OR kind = ?) ORDER BY score LIMIT ?", (q, only, only, n)).fetchall()
    hits = " + ".join("((title LIKE ?) * 2 + (body LIKE ?))" for _ in ts)
    args = [a for t in ts for a in (f"%{t}%", f"%{t}%")]
    return db.execute(f"SELECT kind, ref, -({hits}) AS score, substr(body, 1, 160) AS snip FROM search WHERE ({hits}) > 0 AND (? = '' OR kind = ?) "   # noqa: S608
                      "ORDER BY score LIMIT ?", [*args, *args, only, only, n]).fetchall()


def _detail(db: sqlite3.Connection, kind: str, ref: str) -> dict[str, Any] | None:
    if kind == "document":
        r = db.execute("SELECT id, kind AS doc_kind, title, date, url, domain, status, product, origin FROM documents WHERE id = ?", (ref,)).fetchone()
        return None if r is None else {"id": r["id"], "kind": r["doc_kind"], "type": "document", "title": r["title"], "date": r["date"], "url": r["url"],
                                       "sources": [r["url"]] if r["url"] else [], "product": r["product"], "origin": r["origin"]}
    if kind == "claim":
        r = db.execute("SELECT c.id, c.text, c.status, c.document_id, c.product, c.origin, COALESCE(NULLIF(c.created_at, ''), d.date, '') AS at, "
                       "d.title AS doc_title FROM claims c LEFT JOIN documents d ON d.id = c.document_id WHERE c.id = ?", (ref,)).fetchone()
        if r is None:
            return None
        urls = [x[0] for x in db.execute("SELECT url FROM claim_sources WHERE claim_id = ? ORDER BY relation, url", (ref,))]
        return {"id": r["id"], "kind": "claim", "type": "claim", "title": r["doc_title"] or "", "date": r["at"], "url": "", "sources": urls,
                "document": r["document_id"], "status": r["status"], "product": r["product"], "origin": r["origin"]}
    r = db.execute("SELECT id, kind AS ev_kind, title, date, url, document_id, product, origin FROM events WHERE id = ?", (ref,)).fetchone()
    return None if r is None else {"id": r["id"], "kind": r["ev_kind"], "type": "event", "title": r["title"], "date": r["date"], "url": r["url"],
                                   "sources": [r["url"]] if r["url"] else [], "document": r["document_id"], "product": r["product"], "origin": r["origin"]}


def uses_fts(db: sqlite3.Connection) -> bool:
    return (db.execute("SELECT value FROM meta WHERE key = 'fts'").fetchone() or ["fts5"])[0] == "fts5"


def document_ranking(db: sqlite3.Connection, text: str, *, limit: int = 400) -> list[str]:
    """Ids of the documents best matching ``text``, best first (the lexical ranker retrieval uses when the index is present)."""
    ts = terms(text)
    return [r["ref"] for r in _candidates(db, ts, uses_fts(db), limit, "document")] if ts else []


def search(db: sqlite3.Connection, text: str, *, kinds: set[str] | None = None, since: str = "", until: str = "", limit: int = flags.DEFAULT_LIMIT,
           products: set[str] | None = None) -> list[dict[str, Any]]:
    """Best matches for ``text``. ``kinds`` filters on the hit's own kind (``daily``, ``statement``, ``claim``, ``development``...) or its type
    (``document`` / ``claim`` / ``event``); ``products`` keeps only hits a given product contributed (searched within the best ``_PRODUCT_POOL`` matches)."""
    ts = terms(text)
    if not ts:
        return []
    out: list[dict[str, Any]] = []
    for row in _candidates(db, ts, uses_fts(db), _PRODUCT_POOL if products else max(limit, 1) * _OVERFETCH):
        d = _detail(db, row["kind"], row["ref"])
        if d is None or (since and d["date"] < since) or (until and d["date"] > until):
            continue
        if kinds and d["kind"] not in kinds and d["type"] not in kinds:
            continue
        if products and d["product"] not in products:
            continue
        out.append({**d, "score": round(-row["score"], 4), "snippet": " ".join((row["snip"] or "").split())})
        if len(out) >= limit:
            break
    return out
