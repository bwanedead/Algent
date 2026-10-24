"""
``views/search-index.json``: a compact, client-searchable index of what has a view: entity names and aliases (with the view key that answers for each) and the titles of
the documents the desk has published. The site's API searches it in memory, because Vercel cannot open the SQLite corpus (docs/architecture/views.md, "Agent endpoints").

It deliberately holds no document bodies: free-text search across bodies is the one question this design answers only approximately (titles, names, aliases). If it ever
matters more than that, the server would host a read-only query service; until then the index is one small file that costs R2 nothing per query.
"""

from __future__ import annotations

from typing import Any

from . import entity, flags
from .base import View, make
from .context import ViewContext

DOC_KINDS = ("daily_summary", "daily", "brief", "profile", "article")
FIELDS = {"entities": ["name", "kind", "key", "uses", "aliases"], "documents": ["id", "date", "kind", "title", "url"]}


def _key_of(ctx: ViewContext, row: Any, published: set[str]) -> str | None:
    kind, eid = row["kind"], row["id"]
    if kind == "country":
        return f"country/{row['iso2']}" if row["iso2"] else None
    if kind == "situation":
        tid = eid.split(":", 1)[1]
        return f"situation/{tid}" if ctx.dossier(tid) else None
    key = entity.entity_key(eid, kind)
    return key if key in published else None


def build(ctx: ViewContext, published_keys: set[str] | None = None) -> list[View]:
    """``published_keys``: the view keys this run emits (so the index only points at files that exist)."""
    if ctx.corpus is None:
        return []
    db = ctx.corpus.db
    published = published_keys or set()
    uses = entity.usage(db)
    rows = []
    for r in db.execute("SELECT id, kind, name, aliases, iso2 FROM entities WHERE kind IN ('country','situation','person','org','actor','place','vessel','lab','model')"):
        key = _key_of(ctx, r, published)
        if key:
            import json

            rows.append([r["name"], r["kind"], key, uses.get(r["id"], 0), json.loads(r["aliases"] or "[]")[: flags.SEARCH_ALIASES]])
    rows.sort(key=lambda x: (-x[3], x[0], x[2]))
    docs = [[d["id"], d["date"], d["kind"], d["title"], d["url"]] for d in db.execute(
        f"SELECT id, date, kind, title, url FROM documents WHERE kind IN ({','.join('?' * len(DOC_KINDS))}) AND title != '' ORDER BY date DESC, id LIMIT ?",
        (*DOC_KINDS, flags.SEARCH_DOCUMENTS))]
    body = {"fields": FIELDS, "entities": rows[: flags.SEARCH_ENTITIES], "entities_total": len(rows), "documents": docs}
    as_of = max((d[1] for d in docs), default="")
    return [make("search-index", "search-index", body, as_of=as_of, sources=[("corpus_index", "entities and document titles")])]
