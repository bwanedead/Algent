"""
Evidence trails: turn the corpus ids a decision cited into something a reader can follow (title, date, kind and, where the site has a page for it, a
link). Read-only against the corpus index; with no index the ids are returned bare (the trail is then a list of ids, never an error).
"""

from __future__ import annotations

from typing import Any

SITE = "https://ohmega.monster"


def href_for(kind: str, ident: str, url: str = "") -> str:
    """The site page for an entity (country, situation, place) or a document's own site URL; '' when there is none."""
    if kind == "entity":
        if ident.startswith("country:"):
            return f"/intel/actors/{ident[8:]}"
        if ident.startswith("situation:"):
            return f"/situations/{ident[10:]}"
        if ident.startswith("asset:"):
            return f"/intel/places/{ident[6:]}"
        return ""
    if url.startswith(SITE):
        return url[len(SITE):] or "/"
    return url if url.startswith("/") and not url.startswith("//") else ""


def _row(c: Any, ident: str) -> dict[str, Any]:
    db = c.db
    if ident.startswith("entity:"):
        eid = ident[7:]
        r = db.execute("SELECT name, kind FROM entities WHERE id = ?", (eid,)).fetchone()
        return {"id": ident, "kind": r["kind"] if r else "entity", "title": r["name"] if r else eid, "date": "", "href": href_for("entity", eid)}
    if ident.startswith("series:"):
        return {"id": ident, "kind": "series", "title": ident.split(":", 2)[-1], "date": "", "href": ""}
    r = db.execute("SELECT kind, title, date, url FROM documents WHERE id = ?", (ident,)).fetchone()
    if r:
        return {"id": ident, "kind": r["kind"], "title": r["title"], "date": r["date"], "href": href_for("doc", ident, r["url"] or "")}
    r = db.execute("SELECT c.text AS title, COALESCE(NULLIF(c.created_at, ''), d.date, '') AS date, d.url AS url FROM claims c "
                   "LEFT JOIN documents d ON d.id = c.document_id WHERE c.id = ?", (ident,)).fetchone()
    if r:
        return {"id": ident, "kind": "claim", "title": r["title"], "date": r["date"], "href": href_for("doc", ident, r["url"] or "")}
    r = db.execute("SELECT kind, title, date, url FROM events WHERE id = ?", (ident,)).fetchone()
    if r:
        return {"id": ident, "kind": r["kind"], "title": r["title"], "date": r["date"], "href": href_for("doc", ident, r["url"] or "")}
    return {"id": ident, "kind": "", "title": ident, "date": "", "href": ""}


def resolve(ids: list[str], corpus: Any | None = None) -> list[dict[str, Any]]:
    """One row per id, in order: {id, kind, title, date, href}. Titles are clipped. Best-effort: a lookup error leaves the bare id."""
    if corpus is None:
        from .research import open_corpus

        corpus = open_corpus()
    out = []
    for i in dict.fromkeys(ids):
        try:
            row = _row(corpus, i) if corpus is not None else {"id": i, "kind": "", "title": i, "date": "", "href": ""}
        except Exception:  # noqa: BLE001
            row = {"id": i, "kind": "", "title": i, "date": "", "href": ""}
        row["title"] = " ".join(str(row["title"]).split())[:160]
        out.append(row)
    return out
