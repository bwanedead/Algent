"""
The query API: read-only, fast, and the one door agents and consumers use to ask the corpus.

    c = Corpus.open()                       # read-only connection to the index; raises CorpusMissing when none was built
    c.entity("Hormuz")                      # profile: aliases, latest status, linked situations, top relations, timeline (+ alternatives if ambiguous)
    c.about("Iran", since="2026-10-01")     # documents, claims, events with their sources
    c.timeline("sit_...")                   # events and documents in date order
    c.search("refinery strikes")            # full text over documents, claims and events
    c.related("Iran")                       # what it is most connected to, and why
    c.series("Hormuz")                      # series of an entity, or of a metric id ("bench.", "pulse.*", "chk_hormuz_transits")
    c.stats()                               # row counts, unresolved names, build time, size

Every method returns plain JSON-able dicts and lists, each row carrying its provenance (``product``, ``origin``), so a server view or an MCP
tool is a thin wrapper. No method writes.
"""

from __future__ import annotations

import sqlite3
from pathlib import Path
from typing import Any

from .. import flags, link, paths, schema
from . import about as _about
from . import entity as _entity
from . import graph, resolve, retrieval, series as _series
from . import search as _search


class CorpusMissing(RuntimeError):
    """No index at this location: build one with ``newsroom corpus build``."""


class Corpus:
    def __init__(self, db: sqlite3.Connection, path: Path) -> None:
        self.db, self.path = db, path

    @classmethod
    def open(cls, store: Path | str | None = None) -> Corpus:
        path = paths.db_file(store)
        if not path.is_file():
            raise CorpusMissing(f"no corpus index at {path}; run `newsroom corpus build`")
        return cls(schema.connect(path), path)

    def close(self) -> None:
        self.db.close()

    def __enter__(self) -> Corpus:
        return self

    def __exit__(self, *exc: object) -> None:
        self.close()

    # ── resolving ───────────────────────────────────────────────────────────────────────────
    def find(self, ref: str, kinds: set[str] | None = None) -> list[dict[str, Any]]:
        return resolve.find(self.db, ref, kinds=kinds)

    def _one(self, ref: str) -> tuple[dict[str, Any] | None, list[dict[str, Any]]]:
        return resolve.get(self.db, ref)

    # ── the queries ─────────────────────────────────────────────────────────────────────────
    def entity(self, ref: str) -> dict[str, Any] | None:
        e, others = self._one(ref)
        if e is None:
            return None
        out = _entity.profile(self.db, e)
        if others:
            out["alternatives"] = [{"id": o["id"], "name": o["name"], "kind": o["kind"]} for o in others]
        return out

    def about(self, ref: str, *, since: str = "", until: str = "", kinds: set[str] | None = None, limit: int = flags.DEFAULT_LIMIT) -> dict[str, Any] | None:
        e, others = self._one(ref)
        if e is None:
            return None
        out = {"entity": {"id": e["id"], "name": e["name"], "kind": e["kind"]}, **_about.about(self.db, e["id"], since=since, until=until, kinds=kinds, limit=limit)}
        if others:
            out["alternatives"] = [{"id": o["id"], "name": o["name"], "kind": o["kind"]} for o in others]
        return out

    def timeline(self, ref: str, *, since: str = "", until: str = "", kinds: set[str] | None = None, limit: int = 50) -> list[dict[str, Any]] | None:
        e, _ = self._one(ref)
        return None if e is None else _about.timeline(self.db, e["id"], since=since, until=until, kinds=kinds, limit=limit)

    def search(self, text: str, *, kinds: set[str] | None = None, since: str = "", until: str = "", limit: int = flags.DEFAULT_LIMIT,
               products: set[str] | None = None) -> list[dict[str, Any]]:
        return _search.search(self.db, text, kinds=kinds, since=since, until=until, limit=limit, products=products)

    def related(self, ref: str, *, limit: int = 15, kinds: set[str] | None = None) -> list[dict[str, Any]] | None:
        e, _ = self._one(ref)
        return None if e is None else graph.related(self.db, e["id"], limit=limit, kinds=kinds)

    def series(self, ref: str, *, metric: str = "", since: str = "", until: str = "", points: bool = True, limit: int = 40) -> list[dict[str, Any]]:
        """Series of an entity (``ref``), or of a metric when ``ref`` names no entity but matches a metric id; ``metric`` narrows an entity's series."""
        e, _ = self._one(ref)
        if e is not None:
            return _series.series(self.db, entity_id=e["id"], metric=metric, since=since, until=until, points=points, limit=limit)
        return _series.series(self.db, metric=metric or ref, since=since, until=until, points=points, limit=limit)

    # ── the retrieval slice and the health view ─────────────────────────────────────────────
    def window_docs(self, windows: list[retrieval.Window]) -> list[dict[str, Any]]:
        return retrieval.window_docs(self.db, windows)

    def rank_documents(self, text: str, *, limit: int = 400) -> list[str]:
        return retrieval.rank(self.db, text, limit=limit)

    def stats(self) -> dict[str, Any]:
        from ..build import counts

        db = self.db
        by_kind = lambda table, col: {r[0]: r[1] for r in db.execute(f"SELECT {col}, COUNT(*) FROM {table} GROUP BY 1 ORDER BY 2 DESC")}   # noqa: E731, S608
        dangling = db.execute(
            "SELECT COUNT(*) FROM (SELECT entity_id AS x FROM mentions WHERE asserted = 1 UNION SELECT src_id FROM relations WHERE src_asserted = 1 "
            "UNION SELECT dst_id FROM relations WHERE dst_asserted = 1 UNION SELECT entity_id FROM event_actors WHERE asserted = 1) a "
            "WHERE x NOT IN (SELECT id FROM entities)").fetchone()[0]
        return {"path": str(self.path), "bytes": self.path.stat().st_size, "built_at": schema.meta(db, "built_at"), "fts": schema.meta(db, "fts"),
                "schema_version": schema.meta(db, "schema_version"), "rows": counts(db), "entities_by_kind": by_kind("entities", "kind"),
                "documents_by_kind": by_kind("documents", "kind"), "events_by_kind": by_kind("events", "kind"),
                "observations_by_basis": by_kind("observations", "basis"), "rows_by_product": by_kind("documents", "product"),
                "unresolved": link.unresolved_count(db), "dangling_ids": dangling}

    def unresolved(self, limit: int = 50) -> list[dict[str, Any]]:
        return link.unresolved(self.db, limit=limit)


def available(store: Path | str | None = None) -> bool:
    return paths.available(store)
