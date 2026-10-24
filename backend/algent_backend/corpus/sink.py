"""
``Sink``: the one write path into the index. A source adapter is handed a Sink for the unit it is ingesting and says what it found; the Sink
stamps provenance (product, origin = the unit, ingested_at), keeps text searchable and makes ids and duplicates deterministic.

Adapters never touch SQL. They also never resolve names beyond what their own store already knows: a name that is only text is passed as a
``surface`` and the link pass (``link.py``) resolves it once, against everything declared, after all sources have been read.
"""

from __future__ import annotations

import json
import sqlite3
from collections.abc import Iterable
from typing import Any

from . import flags, schema
from .norm import clip, day, digest, domain_of, norm


def clear_unit(db: sqlite3.Connection, unit: str) -> None:
    """Forget everything one unit contributed (before re-ingesting it, or when its source is gone)."""
    for table in schema.UNIT_TABLES:
        db.execute(f"DELETE FROM {table} WHERE origin = ?", (unit,))   # noqa: S608 - table names are constants
    db.execute("DELETE FROM search WHERE origin = ?", (unit,))
    db.execute("DELETE FROM ingest_state WHERE unit = ?", (unit,))


class Sink:
    def __init__(self, db: sqlite3.Connection, product: str, unit: str, now: str) -> None:
        self.db, self.product, self.unit, self.now = db, product, unit, now
        self.rows = 0

    def _stamp(self) -> tuple[str, str, str]:
        return self.product, self.unit, self.now

    def _search(self, kind: str, ref: str, title: str, body: str) -> None:
        self.db.execute("INSERT INTO search (title, body, ref, kind, origin) VALUES (?,?,?,?,?)",
                        (clip(title, 400), clip(body, flags.BODY_CHARS), ref, kind, self.unit))

    # ── entities ──────────────────────────────────────────────────────────────────────────────
    def declare(self, entity_id: str, kind: str, name: str, *, aliases: Iterable[str] = (), iso2: str | None = None, lat: float | None = None,
                lon: float | None = None, attrs: dict[str, Any] | None = None, rank: int = flags.RANK_DECLARED) -> str:
        """Say what this source knows about an entity. Several sources may declare one id; ``link.materialise`` merges them deterministically."""
        al = sorted({a.strip() for a in aliases if a and a.strip() and norm(a) != norm(name)})
        self.db.execute("INSERT OR REPLACE INTO entity_decl VALUES (?,?,?,?,?,?,?,?,?,?,?,?)",
                        (entity_id, self.unit, rank, kind, name.strip() or entity_id, iso2, lat, lon,
                         json.dumps(attrs or {}, ensure_ascii=False, sort_keys=True), json.dumps(al, ensure_ascii=False), self.product, self.now))
        self.rows += 1
        return entity_id

    # ── documents, claims, sources ───────────────────────────────────────────────────────────
    def document(self, doc_id: str, kind: str, *, date: str = "", title: str = "", body: str = "", domain: str = "", url: str = "",
                 status: str = "") -> str:
        body = clip(body, flags.BODY_CHARS)
        self.db.execute("INSERT OR REPLACE INTO documents VALUES (?,?,?,?,?,?,?,?,?,?,?)",
                        (doc_id, kind, domain, day(date) or str(date or ""), title.strip(), url, status, body, *self._stamp()))
        self._search("document", doc_id, title, body)
        self.rows += 1
        return doc_id

    def claim(self, claim_id: str, text: str, *, document_id: str = "", status: str = "", grounding: str = "", confidence: str = "",
              created_at: str = "") -> str:
        self.db.execute("INSERT OR REPLACE INTO claims VALUES (?,?,?,?,?,?,?,?,?,?)",
                        (claim_id, text.strip(), status, grounding, str(confidence or ""), document_id, created_at, *self._stamp()))
        self._search("claim", claim_id, "", text)
        self.rows += 1
        return claim_id

    def cite(self, claim_id: str, url: str, *, title: str = "", fetched_at: str = "", relation: str = "supports") -> None:
        """A source for a claim. Sources are shared by url across claims; the longest title and the newest fetch win, whatever the order."""
        if not url:
            return
        self.db.execute(
            "INSERT INTO sources VALUES (?,?,?,?) ON CONFLICT(url) DO UPDATE SET "
            "title = CASE WHEN length(excluded.title) > length(title) OR (length(excluded.title) = length(title) AND excluded.title > title) "
            "THEN excluded.title ELSE title END, fetched_at = max(fetched_at, excluded.fetched_at)",
            (url, domain_of(url), title.strip(), fetched_at))
        self.db.execute("INSERT OR REPLACE INTO claim_sources VALUES (?,?,?,?)", (claim_id, url, relation, self.unit))
        self.rows += 1

    # ── graph ─────────────────────────────────────────────────────────────────────────────────
    def mention(self, *, entity: str | None = None, surface: str = "", document: str = "", claim: str = "", role: str = "", date: str = "") -> None:
        """An entity appears in a document or claim: by id when the adapter knows it, else by the text it was written as."""
        if not entity and not norm(surface):
            return
        sn = norm(surface)
        mid = digest(self.unit, entity or sn, document, claim, role)
        self.db.execute("INSERT OR REPLACE INTO mentions VALUES (?,?,?,?,?,?,?,?,?,?,?,?)",
                        (mid, entity, int(bool(entity)), surface.strip(), sn, document, claim, role, day(date), *self._stamp()))
        self.rows += 1

    def relation(self, rel: str, *, src: str | None = None, src_surface: str = "", dst: str | None = None, dst_surface: str = "",
                 document: str = "", claim: str = "", date: str = "", note: str = "") -> None:
        if not (src or norm(src_surface)) or not (dst or norm(dst_surface)):
            return
        rid = digest(self.unit, rel, src or norm(src_surface), dst or norm(dst_surface), document, claim, day(date))
        self.db.execute("INSERT OR REPLACE INTO relations VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                        (rid, src, int(bool(src)), src_surface.strip(), norm(src_surface), dst, int(bool(dst)), dst_surface.strip(), norm(dst_surface),
                         rel, document, claim, day(date), clip(note, 600), *self._stamp()))
        self.rows += 1

    # ── series and happenings ────────────────────────────────────────────────────────────────
    def observation(self, metric: str, ts: str, value: float, *, entity: str = "", unit: str = "", basis: str = "", label: str = "",
                    source_url: str = "", note: str = "") -> None:
        """One point of a series. ``basis`` follows the stats registry: official | our_count | our_derived | model (| reported for a cited figure)."""
        oid = digest(self.unit, entity, metric, ts)
        self.db.execute("INSERT OR REPLACE INTO observations VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)",
                        (oid, entity, metric, ts, float(value), unit, basis, label, source_url, clip(note, 400), *self._stamp()))
        self.rows += 1

    def event(self, event_id: str, kind: str, *, date: str, title: str, detail: str = "", status: str = "", end_date: str = "", place: str = "",
              place_id: str | None = None, lat: float | None = None, lon: float | None = None, document: str = "", url: str = "",
              actors: Iterable[str] = (), actor_ids: Iterable[str] = (), role: str = "actor") -> str:
        detail = clip(detail, flags.BODY_CHARS)
        self.db.execute("INSERT OR REPLACE INTO events VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                        (event_id, kind, day(date) or str(date or ""), day(end_date), title.strip(), detail, status, place.strip(), norm(place), place_id,
                         int(bool(place_id)), lat, lon, document, url, *self._stamp()))
        for a in actors:
            if norm(a):
                self.db.execute("INSERT OR REPLACE INTO event_actors VALUES (?,?,?,?,?,?,?)", (event_id, None, 0, a.strip(), norm(a), role, self.unit))
        for eid in actor_ids:
            self.db.execute("INSERT OR REPLACE INTO event_actors VALUES (?,?,?,?,?,?,?)", (event_id, eid, 1, eid, norm(eid), role, self.unit))
        self._search("event", event_id, title, detail)
        self.rows += 1
        return event_id
