"""
"Everything we know about X since Y, with sources": documents, claims and events that involve an entity, each with where it came from and the
URLs behind it. ``timeline`` is the same material in date order.
"""

from __future__ import annotations

import sqlite3
from typing import Any

from .. import flags


def _in(values: set[str]) -> tuple[str, list[str]]:
    vs = sorted(values)
    return ",".join("?" * len(vs)), vs


def claim_sources(db: sqlite3.Connection, claim_ids: list[str]) -> dict[str, list[dict[str, str]]]:
    out: dict[str, list[dict[str, str]]] = {c: [] for c in claim_ids}
    for i in range(0, len(claim_ids), 500):
        chunk = claim_ids[i:i + 500]
        marks = ",".join("?" * len(chunk))
        for r in db.execute(f"SELECT cs.claim_id, cs.url, cs.relation, s.title, s.domain FROM claim_sources cs "      # noqa: S608
                            f"LEFT JOIN sources s ON s.url = cs.url WHERE cs.claim_id IN ({marks}) ORDER BY cs.relation, cs.url", chunk):
            out[r["claim_id"]].append({"url": r["url"], "title": r["title"] or "", "domain": r["domain"] or "", "relation": r["relation"]})
    return out


def documents(db: sqlite3.Connection, entity_id: str, *, since: str = "", until: str = "", kinds: set[str] | None = None,
              limit: int = flags.DEFAULT_LIMIT) -> list[dict[str, Any]]:
    sql = ("SELECT d.id, d.kind, d.domain, d.date, d.title, d.url, d.status, d.product, d.origin, d.ingested_at, "
           "group_concat(DISTINCT m.role) AS roles FROM mentions m JOIN documents d ON d.id = m.document_id "
           "WHERE m.entity_id = ? AND d.date >= ?")
    args: list[Any] = [entity_id, since]
    if until:
        sql, args = sql + " AND d.date <= ?", [*args, until]
    if kinds:
        marks, vs = _in(kinds)
        sql, args = sql + f" AND d.kind IN ({marks})", [*args, *vs]
    rows = db.execute(sql + " GROUP BY d.id ORDER BY d.date DESC, d.id LIMIT ?", [*args, limit]).fetchall()
    out = [dict(r) for r in rows]
    for d in out:                                                          # the URLs behind a document: its own, plus those of the claims it holds
        urls = [r[0] for r in db.execute("SELECT DISTINCT cs.url FROM claims c JOIN claim_sources cs ON cs.claim_id = c.id WHERE c.document_id = ? "
                                         "ORDER BY cs.url LIMIT 6", (d["id"],))]
        d["sources"] = list(dict.fromkeys([u for u in (d["url"], *urls) if u]))
    return out


def claims(db: sqlite3.Connection, entity_id: str, *, since: str = "", limit: int = flags.DEFAULT_LIMIT) -> list[dict[str, Any]]:
    rows = db.execute(
        "SELECT c.id, c.text, c.status, c.grounding, c.confidence, c.document_id, c.created_at, c.product, c.origin, c.ingested_at, "
        "COALESCE(NULLIF(c.created_at, ''), d.date, '') AS at FROM mentions m JOIN claims c ON c.id = m.claim_id "
        "LEFT JOIN documents d ON d.id = c.document_id WHERE m.entity_id = ? AND COALESCE(NULLIF(c.created_at, ''), d.date, '') >= ? "
        "GROUP BY c.id ORDER BY at DESC, c.id LIMIT ?", (entity_id, since, limit)).fetchall()
    out = [dict(r) for r in rows]
    srcs = claim_sources(db, [c["id"] for c in out])
    for c in out:
        c["sources"] = srcs[c["id"]]
    return out


def events(db: sqlite3.Connection, entity_id: str, *, since: str = "", until: str = "", kinds: set[str] | None = None,
           limit: int = flags.DEFAULT_LIMIT) -> list[dict[str, Any]]:
    """Events at the entity (a place) or involving it (an actor, a market, a situation)."""
    sql = ("SELECT e.id, e.kind, e.date, e.end_date, e.title, e.detail, e.status, e.place, e.lat, e.lon, e.document_id, e.url, e.product, e.origin, "
           "e.ingested_at FROM events e WHERE (e.place_id = ? OR e.id IN (SELECT event_id FROM event_actors WHERE entity_id = ?)) AND e.date >= ?")
    args: list[Any] = [entity_id, entity_id, since]
    if until:
        sql, args = sql + " AND e.date <= ?", [*args, until]
    if kinds:
        marks, vs = _in(kinds)
        sql, args = sql + f" AND e.kind IN ({marks})", [*args, *vs]
    out = []
    for r in db.execute(sql + " ORDER BY e.date DESC, e.id LIMIT ?", [*args, limit]):
        e = dict(r)
        e["sources"] = [e["url"]] if e["url"] else []
        out.append(e)
    return out


def about(db: sqlite3.Connection, entity_id: str, *, since: str = "", until: str = "", kinds: set[str] | None = None,
          limit: int = flags.DEFAULT_LIMIT) -> dict[str, list[dict[str, Any]]]:
    """Documents, claims and events about the entity. ``kinds`` filters document kinds and event kinds; the words ``claim`` / ``event`` / ``document``
    select whole sections (``{"claim"}`` alone returns only claims)."""
    sections = {k for k in (kinds or set()) if k in ("claim", "event", "document")}
    kind_filter = (kinds or set()) - sections or None
    want = lambda s: not sections or s in sections                              # noqa: E731
    return {
        "documents": documents(db, entity_id, since=since, until=until, kinds=kind_filter, limit=limit) if want("document") else [],
        "claims": claims(db, entity_id, since=since, limit=limit) if want("claim") and not kind_filter else [],
        "events": events(db, entity_id, since=since, until=until, kinds=kind_filter if sections else None, limit=limit) if want("event") else [],
    }


def timeline(db: sqlite3.Connection, entity_id: str, *, since: str = "", until: str = "", kinds: set[str] | None = None,
             limit: int = 50) -> list[dict[str, Any]]:
    """Events and documents involving the entity, oldest first. A development that several dailies repeat shows once (the first report that carried it)."""
    got = about(db, entity_id, since=since, until=until, kinds=kinds or {"event", "document"}, limit=limit * 3)
    items = [{"date": e["date"], "type": "event", "kind": e["kind"], "id": e["id"], "title": e["title"], "detail": e["detail"], "status": e["status"],
              "place": e["place"], "sources": e["sources"], "document": e["document_id"], "product": e["product"]} for e in got["events"]]
    items += [{"date": d["date"], "type": "document", "kind": d["kind"], "id": d["id"], "title": d["title"], "detail": "", "status": d["status"],
               "place": "", "sources": d["sources"], "document": d["id"], "product": d["product"]} for d in got["documents"]]
    seen: set[tuple[str, str, str]] = set()
    out = []
    for it in sorted(items, key=lambda i: (i["date"], i["type"], i["id"])):
        key = (it["date"], it["type"], it["title"])
        if key not in seen:
            seen.add(key)
            out.append(it)
    return out[-limit:]
