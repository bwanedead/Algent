"""
The index layout and how to open it. One SQLite file, WAL, derived from the JSON record and safe to delete.

Normalised and graph-shaped: ``entities`` are the nodes, ``relations`` the typed edges (with evidence), ``documents`` / ``claims`` / ``sources``
the text and its provenance, ``mentions`` the entity-in-document links, ``observations`` the time series and ``events`` the dated happenings.
Every content row carries ``product`` (which registry product it came from), ``origin`` (the unit of that product's store it was read from;
``ingest_state`` says which file or ledger line that is) and ``ingested_at``. Replacing a changed unit is "delete rows where origin = unit, insert".

``entity_decl`` holds what each source *said* about an entity; ``entities`` and ``entity_alias`` are materialised from it at the end of a build
(``link.py``), which is why the result does not depend on the order sources were read in.
"""

from __future__ import annotations

import sqlite3
from pathlib import Path

from . import flags

_CORE = """
CREATE TABLE IF NOT EXISTS meta (key TEXT PRIMARY KEY, value TEXT);
CREATE TABLE IF NOT EXISTS ingest_state (
    unit TEXT PRIMARY KEY, product TEXT NOT NULL, source TEXT NOT NULL, path TEXT NOT NULL DEFAULT '',
    date TEXT NOT NULL DEFAULT '', fingerprint TEXT NOT NULL, ingested_at TEXT NOT NULL);
CREATE INDEX IF NOT EXISTS ix_state_source ON ingest_state(source);
CREATE TABLE IF NOT EXISTS source_state (source TEXT PRIMARY KEY, watermark TEXT NOT NULL, ingested_at TEXT NOT NULL);

CREATE TABLE IF NOT EXISTS entity_decl (
    entity_id TEXT NOT NULL, origin TEXT NOT NULL, rank INTEGER NOT NULL, kind TEXT NOT NULL, name TEXT NOT NULL,
    iso2 TEXT, lat REAL, lon REAL, attrs TEXT NOT NULL DEFAULT '{}', aliases TEXT NOT NULL DEFAULT '[]',
    product TEXT NOT NULL, ingested_at TEXT NOT NULL, PRIMARY KEY (entity_id, origin));
CREATE INDEX IF NOT EXISTS ix_decl_origin ON entity_decl(origin);

CREATE TABLE IF NOT EXISTS entities (
    id TEXT PRIMARY KEY, kind TEXT NOT NULL, name TEXT NOT NULL, aliases TEXT NOT NULL DEFAULT '[]', iso2 TEXT,
    lat REAL, lon REAL, attrs TEXT NOT NULL DEFAULT '{}', product TEXT NOT NULL, origin TEXT NOT NULL, ingested_at TEXT NOT NULL);
CREATE INDEX IF NOT EXISTS ix_entities_kind ON entities(kind);
CREATE INDEX IF NOT EXISTS ix_entities_iso2 ON entities(iso2);
CREATE TABLE IF NOT EXISTS entity_alias (norm TEXT NOT NULL, entity_id TEXT NOT NULL, alias TEXT NOT NULL, PRIMARY KEY (norm, entity_id));
CREATE INDEX IF NOT EXISTS ix_alias_entity ON entity_alias(entity_id);
-- ids declared for one real thing, folded into the canonical one (identity.py); rows asserting an old id are rewritten to the canonical id
CREATE TABLE IF NOT EXISTS entity_merge (old_id TEXT PRIMARY KEY, canon_id TEXT NOT NULL);

CREATE TABLE IF NOT EXISTS documents (
    id TEXT PRIMARY KEY, kind TEXT NOT NULL, domain TEXT NOT NULL DEFAULT '', date TEXT NOT NULL DEFAULT '', title TEXT NOT NULL DEFAULT '',
    url TEXT NOT NULL DEFAULT '', status TEXT NOT NULL DEFAULT '', body TEXT NOT NULL DEFAULT '',
    product TEXT NOT NULL, origin TEXT NOT NULL, ingested_at TEXT NOT NULL);
CREATE INDEX IF NOT EXISTS ix_documents_kind_date ON documents(kind, date);
CREATE INDEX IF NOT EXISTS ix_documents_origin ON documents(origin);

CREATE TABLE IF NOT EXISTS claims (
    id TEXT PRIMARY KEY, text TEXT NOT NULL, status TEXT NOT NULL DEFAULT '', grounding TEXT NOT NULL DEFAULT '', confidence TEXT NOT NULL DEFAULT '',
    document_id TEXT NOT NULL DEFAULT '', created_at TEXT NOT NULL DEFAULT '', product TEXT NOT NULL, origin TEXT NOT NULL, ingested_at TEXT NOT NULL);
CREATE INDEX IF NOT EXISTS ix_claims_doc ON claims(document_id);
CREATE INDEX IF NOT EXISTS ix_claims_origin ON claims(origin);

CREATE TABLE IF NOT EXISTS sources (url TEXT PRIMARY KEY, domain TEXT NOT NULL DEFAULT '', title TEXT NOT NULL DEFAULT '', fetched_at TEXT NOT NULL DEFAULT '');
CREATE TABLE IF NOT EXISTS claim_sources (
    claim_id TEXT NOT NULL, url TEXT NOT NULL, relation TEXT NOT NULL DEFAULT 'supports', origin TEXT NOT NULL, PRIMARY KEY (claim_id, url, relation));
CREATE INDEX IF NOT EXISTS ix_cs_url ON claim_sources(url);
CREATE INDEX IF NOT EXISTS ix_cs_origin ON claim_sources(origin);

CREATE TABLE IF NOT EXISTS mentions (
    id TEXT PRIMARY KEY, entity_id TEXT, asserted INTEGER NOT NULL DEFAULT 0, surface TEXT NOT NULL DEFAULT '', surface_norm TEXT NOT NULL DEFAULT '',
    document_id TEXT NOT NULL DEFAULT '', claim_id TEXT NOT NULL DEFAULT '', role TEXT NOT NULL DEFAULT '', date TEXT NOT NULL DEFAULT '',
    product TEXT NOT NULL, origin TEXT NOT NULL, ingested_at TEXT NOT NULL);
CREATE INDEX IF NOT EXISTS ix_mentions_entity ON mentions(entity_id, date);
CREATE INDEX IF NOT EXISTS ix_mentions_doc ON mentions(document_id);
CREATE INDEX IF NOT EXISTS ix_mentions_norm ON mentions(surface_norm);
CREATE INDEX IF NOT EXISTS ix_mentions_origin ON mentions(origin);

CREATE TABLE IF NOT EXISTS relations (
    id TEXT PRIMARY KEY, src_id TEXT, src_asserted INTEGER NOT NULL DEFAULT 0, src_surface TEXT NOT NULL DEFAULT '', src_norm TEXT NOT NULL DEFAULT '',
    dst_id TEXT, dst_asserted INTEGER NOT NULL DEFAULT 0, dst_surface TEXT NOT NULL DEFAULT '', dst_norm TEXT NOT NULL DEFAULT '',
    rel TEXT NOT NULL, document_id TEXT NOT NULL DEFAULT '', claim_id TEXT NOT NULL DEFAULT '', date TEXT NOT NULL DEFAULT '', note TEXT NOT NULL DEFAULT '',
    product TEXT NOT NULL, origin TEXT NOT NULL, ingested_at TEXT NOT NULL);
CREATE INDEX IF NOT EXISTS ix_rel_src ON relations(src_id, rel);
CREATE INDEX IF NOT EXISTS ix_rel_dst ON relations(dst_id, rel);
CREATE INDEX IF NOT EXISTS ix_rel_origin ON relations(origin);

CREATE TABLE IF NOT EXISTS observations (
    id TEXT PRIMARY KEY, entity_id TEXT NOT NULL DEFAULT '', metric TEXT NOT NULL, ts TEXT NOT NULL, value REAL NOT NULL, unit TEXT NOT NULL DEFAULT '',
    basis TEXT NOT NULL DEFAULT '', label TEXT NOT NULL DEFAULT '', source_url TEXT NOT NULL DEFAULT '', note TEXT NOT NULL DEFAULT '',
    product TEXT NOT NULL, origin TEXT NOT NULL, ingested_at TEXT NOT NULL);
CREATE INDEX IF NOT EXISTS ix_obs_entity ON observations(entity_id, metric, ts);
CREATE INDEX IF NOT EXISTS ix_obs_metric ON observations(metric, ts);
CREATE INDEX IF NOT EXISTS ix_obs_origin ON observations(origin);

CREATE TABLE IF NOT EXISTS events (
    id TEXT PRIMARY KEY, kind TEXT NOT NULL, date TEXT NOT NULL DEFAULT '', end_date TEXT NOT NULL DEFAULT '', title TEXT NOT NULL DEFAULT '',
    detail TEXT NOT NULL DEFAULT '', status TEXT NOT NULL DEFAULT '', place TEXT NOT NULL DEFAULT '', place_norm TEXT NOT NULL DEFAULT '', place_id TEXT,
    place_asserted INTEGER NOT NULL DEFAULT 0, lat REAL, lon REAL, document_id TEXT NOT NULL DEFAULT '', url TEXT NOT NULL DEFAULT '',
    product TEXT NOT NULL, origin TEXT NOT NULL, ingested_at TEXT NOT NULL);
CREATE INDEX IF NOT EXISTS ix_events_date ON events(date, kind);
CREATE INDEX IF NOT EXISTS ix_events_place ON events(place_id);
CREATE INDEX IF NOT EXISTS ix_events_origin ON events(origin);
CREATE TABLE IF NOT EXISTS event_actors (
    event_id TEXT NOT NULL, entity_id TEXT, asserted INTEGER NOT NULL DEFAULT 0, surface TEXT NOT NULL DEFAULT '', surface_norm TEXT NOT NULL DEFAULT '',
    role TEXT NOT NULL DEFAULT 'actor', origin TEXT NOT NULL, PRIMARY KEY (event_id, surface_norm, role));
CREATE INDEX IF NOT EXISTS ix_ea_entity ON event_actors(entity_id);
CREATE INDEX IF NOT EXISTS ix_ea_origin ON event_actors(origin);
"""

#: Every table whose rows belong to one ingestion unit (``origin``): replacing a unit deletes from all of them (and from ``search``).
UNIT_TABLES = ("entity_decl", "documents", "claims", "claim_sources", "mentions", "relations", "observations", "events", "event_actors")
#: Row counts ``stats`` reports.
COUNTED = ("entities", "entity_alias", "documents", "claims", "sources", "claim_sources", "mentions", "relations", "observations", "events", "event_actors")

_FTS = ("CREATE VIRTUAL TABLE IF NOT EXISTS search USING fts5(title, body, ref UNINDEXED, kind UNINDEXED, origin UNINDEXED, "
        "tokenize='porter unicode61 remove_diacritics 2')")
#: The same shape without FTS5 (a Python build that lacks it): queries fall back to LIKE (``query/search.py``).
_PLAIN = ("CREATE TABLE IF NOT EXISTS search (title TEXT, body TEXT, ref TEXT, kind TEXT, origin TEXT);"
          "CREATE INDEX IF NOT EXISTS ix_search_origin ON search(origin)")


def fts5_available() -> bool:
    try:
        c = sqlite3.connect(":memory:")
        c.execute("CREATE VIRTUAL TABLE t USING fts5(a)")
        c.close()
        return True
    except sqlite3.Error:
        return False


def db_path(store: Path | str) -> Path:
    return Path(store) / flags.DB_NAME


def create(db: sqlite3.Connection, *, fts: bool | None = None) -> bool:
    """Create every table; returns whether search uses FTS5. The choice is recorded in ``meta`` so readers know without probing."""
    use = fts5_available() if fts is None else fts
    db.executescript(_CORE)
    db.executescript(_FTS if use else _PLAIN)
    db.execute("INSERT OR REPLACE INTO meta VALUES ('schema_version', ?)", (str(flags.SCHEMA_VERSION),))
    db.execute("INSERT OR REPLACE INTO meta VALUES ('fts', ?)", ("fts5" if use else "like",))
    db.commit()
    return use


def connect(path: Path | str, *, write: bool = False) -> sqlite3.Connection:
    """Open the index. Readers get a read-only connection (they can never change the index, let alone the record)."""
    p = Path(path)
    if write:
        p.parent.mkdir(parents=True, exist_ok=True)
        db = sqlite3.connect(p, timeout=flags.BUSY_TIMEOUT_S)
        db.execute("PRAGMA journal_mode=WAL")
        db.execute("PRAGMA synchronous=NORMAL")
    else:
        db = sqlite3.connect(f"file:{p.as_posix()}?mode=ro", uri=True, timeout=flags.BUSY_TIMEOUT_S)
    db.row_factory = sqlite3.Row
    return db


def meta(db: sqlite3.Connection, key: str, default: str = "") -> str:
    try:
        row = db.execute("SELECT value FROM meta WHERE key = ?", (key,)).fetchone()
    except sqlite3.Error:
        return default
    return row[0] if row else default


def schema_current(db: sqlite3.Connection) -> bool:
    return meta(db, "schema_version") == str(flags.SCHEMA_VERSION)
