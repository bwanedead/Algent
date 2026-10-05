"""
The library store: one SQLite file with an FTS5 index over the latest revision of every page.

    <root>/library.db        root = $ALGENT_LIBRARY_STORE or ``library_store`` under the working directory

Tables: ``documents`` (every revision ever kept; ``latest=1`` marks the one search sees), ``docs_fts``
(external-content FTS5 over title+text of latest rows only — text is stored once), ``feed_state``
(validators, failures, parking per feed URL) and ``page_failures`` (urls that would not read).

Append-only in spirit: a changed page is a NEW row (revision n+1) and the old one stops being ``latest``;
an unchanged page writes nothing. Only ``enforce_retention`` ever deletes.

Retention (bounds the disk on a weak laptop; see docs/architecture/library.md):
  1. superseded revisions are dropped after ``REVISION_KEEP_DAYS``;
  2. a page is dropped when older than its age limit (``AGE_LIMIT_DAYS``: news 90 d, analysis 365 d, primary 730 d);
  3. if the live data still exceeds ``MAX_DB_BYTES`` the oldest pages go first, news before analysis before primary,
     until the db is back under 90% of the budget.
Text is capped at ``MAX_TEXT_CHARS`` per page — enough for the lead and body of an article to be found by its
content, small enough that ~300 pages/day stay near 3 MB/day of text plus index.
"""

from __future__ import annotations

import hashlib
import os
import sqlite3
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

from .sources import ANALYSIS_KINDS, PRIMARY_KINDS

_STORE_ENV = "ALGENT_LIBRARY_STORE"
_DEFAULT_DIR = "library_store"
DB_NAME = "library.db"

MAX_TEXT_CHARS = 12_000
MAX_DB_BYTES = 400_000_000
REVISION_KEEP_DAYS = 14
AGE_LIMIT_DAYS = {"news": 90, "analysis": 365, "primary": 730}

_SCHEMA = """
CREATE TABLE IF NOT EXISTS documents (
  id INTEGER PRIMARY KEY, url TEXT NOT NULL, source_id TEXT NOT NULL, domain TEXT NOT NULL,
  kind TEXT NOT NULL, region TEXT NOT NULL DEFAULT '', title TEXT NOT NULL DEFAULT '',
  published TEXT NOT NULL DEFAULT '', fetched_at TEXT NOT NULL, stamp TEXT NOT NULL DEFAULT '',
  text TEXT NOT NULL DEFAULT '', text_hash TEXT NOT NULL, via TEXT NOT NULL DEFAULT '',
  revision INTEGER NOT NULL DEFAULT 1, latest INTEGER NOT NULL DEFAULT 1);
CREATE INDEX IF NOT EXISTS documents_url ON documents(url, revision);
CREATE INDEX IF NOT EXISTS documents_source ON documents(source_id, latest);
CREATE VIRTUAL TABLE IF NOT EXISTS docs_fts USING fts5(
  title, text, content='documents', content_rowid='id', tokenize='porter unicode61 remove_diacritics 2');
CREATE TABLE IF NOT EXISTS feed_state (
  feed_url TEXT PRIMARY KEY, source_id TEXT NOT NULL, etag TEXT NOT NULL DEFAULT '',
  last_modified TEXT NOT NULL DEFAULT '', last_polled TEXT NOT NULL DEFAULT '', last_ok TEXT NOT NULL DEFAULT '',
  failures INTEGER NOT NULL DEFAULT 0, parked_until TEXT NOT NULL DEFAULT '', last_error TEXT NOT NULL DEFAULT '');
CREATE TABLE IF NOT EXISTS page_failures (
  url TEXT PRIMARY KEY, source_id TEXT NOT NULL, failures INTEGER NOT NULL DEFAULT 0,
  last_error TEXT NOT NULL DEFAULT '', last_attempt TEXT NOT NULL DEFAULT '', parked INTEGER NOT NULL DEFAULT 0);
"""


@dataclass
class Doc:
    url: str
    source_id: str
    domain: str
    kind: str
    title: str
    text: str
    fetched_at: str
    region: str = ""
    published: str = ""
    stamp: str = ""
    via: str = ""


def store_dir() -> Path:
    return Path(os.environ.get(_STORE_ENV) or _DEFAULT_DIR)


def db_path() -> Path:
    return store_dir() / DB_NAME


def connect(*, create: bool = True) -> sqlite3.Connection | None:
    """Open (and initialise) the db. With ``create=False`` an absent store returns None — reads must not mint files."""
    path = db_path()
    if not path.is_file():
        if not create:
            return None
        path.parent.mkdir(parents=True, exist_ok=True)
        fresh = sqlite3.connect(path)
        fresh.execute("PRAGMA auto_vacuum=INCREMENTAL")        # must precede the first table
        fresh.close()
    conn = sqlite3.connect(path, timeout=30)
    conn.row_factory = sqlite3.Row
    conn.executescript(_SCHEMA)
    return conn


def now_iso() -> str:
    return datetime.now(UTC).isoformat(timespec="seconds")


def _hash(text: str) -> str:
    return hashlib.sha256(" ".join(text.split()).encode("utf-8")).hexdigest()[:20]


def _fts_insert(conn: sqlite3.Connection, rowid: int, title: str, text: str) -> None:
    conn.execute("INSERT INTO docs_fts(rowid, title, text) VALUES (?,?,?)", (rowid, title, text))


def _fts_delete(conn: sqlite3.Connection, rowid: int, title: str, text: str) -> None:
    conn.execute("INSERT INTO docs_fts(docs_fts, rowid, title, text) VALUES ('delete',?,?,?)", (rowid, title, text))


def known_stamp(conn: sqlite3.Connection, url: str) -> str | None:
    """The feed stamp stored with the latest revision of ``url``; None when the url was never indexed."""
    row = conn.execute("SELECT stamp FROM documents WHERE url=? AND latest=1", (url,)).fetchone()
    return None if row is None else row["stamp"]


def add_document(conn: sqlite3.Connection, doc: Doc) -> str:
    """Store ``doc``: returns "new", "revised" (text changed: new revision row) or "unchanged" (only the stamp moves)."""
    text = doc.text[:MAX_TEXT_CHARS]
    digest = _hash(text)
    prev = conn.execute("SELECT * FROM documents WHERE url=? AND latest=1", (doc.url,)).fetchone()
    with conn:
        if prev is not None and prev["text_hash"] == digest and prev["title"] == doc.title:
            conn.execute("UPDATE documents SET stamp=? WHERE id=?", (doc.stamp, prev["id"]))
            return "unchanged"
        revision = 1
        if prev is not None:
            _fts_delete(conn, prev["id"], prev["title"], prev["text"])
            conn.execute("UPDATE documents SET latest=0 WHERE id=?", (prev["id"],))
            revision = prev["revision"] + 1
        cur = conn.execute(
            "INSERT INTO documents(url, source_id, domain, kind, region, title, published, fetched_at, stamp, text,"
            " text_hash, via, revision, latest) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,1)",
            (doc.url, doc.source_id, doc.domain, doc.kind, doc.region, doc.title, doc.published, doc.fetched_at,
             doc.stamp, text, digest, doc.via, revision))
        _fts_insert(conn, cur.lastrowid, doc.title, text)
    return "new" if prev is None else "revised"


# -- crawl state ---------------------------------------------------------------------------------
def feed_state(conn: sqlite3.Connection, feed_url: str) -> sqlite3.Row | None:
    return conn.execute("SELECT * FROM feed_state WHERE feed_url=?", (feed_url,)).fetchone()


def save_feed_state(conn: sqlite3.Connection, feed_url: str, source_id: str, **fields: Any) -> None:
    with conn:
        conn.execute("INSERT OR IGNORE INTO feed_state(feed_url, source_id) VALUES (?,?)", (feed_url, source_id))
        if fields:
            sets = ", ".join(f"{k}=?" for k in fields)
            conn.execute(f"UPDATE feed_state SET {sets} WHERE feed_url=?", (*fields.values(), feed_url))  # noqa: S608 - keys are ours


def page_parked(conn: sqlite3.Connection, url: str) -> bool:
    row = conn.execute("SELECT parked FROM page_failures WHERE url=?", (url,)).fetchone()
    return bool(row and row["parked"])


def record_page_failure(conn: sqlite3.Connection, url: str, source_id: str, error: str, *, park_after: int,
                        park_now: bool = False) -> bool:
    """Count a failed read; park the url (never retried) after ``park_after`` failures. Returns whether parked."""
    row = conn.execute("SELECT failures FROM page_failures WHERE url=?", (url,)).fetchone()
    failures = (row["failures"] if row else 0) + 1
    parked = park_now or failures >= park_after
    with conn:
        conn.execute("INSERT INTO page_failures(url, source_id, failures, last_error, last_attempt, parked) VALUES (?,?,?,?,?,?)"
                     " ON CONFLICT(url) DO UPDATE SET failures=excluded.failures, last_error=excluded.last_error,"
                     " last_attempt=excluded.last_attempt, parked=excluded.parked",
                     (url, source_id, failures, error[:200], now_iso(), int(parked)))
    return parked


# -- retention -----------------------------------------------------------------------------------
def _tier(kind: str) -> str:
    return "primary" if kind in PRIMARY_KINDS else "analysis" if kind in ANALYSIS_KINDS else "news"


def _delete_ids(conn: sqlite3.Connection, ids: list[int]) -> None:
    for i in range(0, len(ids), 500):
        chunk = ids[i:i + 500]
        marks = ",".join("?" * len(chunk))
        for r in conn.execute(f"SELECT id, title, text, latest FROM documents WHERE id IN ({marks})", chunk).fetchall():  # noqa: S608
            if r["latest"]:
                _fts_delete(conn, r["id"], r["title"], r["text"])
        conn.execute(f"DELETE FROM documents WHERE id IN ({marks})", chunk)  # noqa: S608


def live_bytes(conn: sqlite3.Connection) -> int:
    pages = conn.execute("PRAGMA page_count").fetchone()[0] - conn.execute("PRAGMA freelist_count").fetchone()[0]
    return pages * conn.execute("PRAGMA page_size").fetchone()[0]


def enforce_retention(conn: sqlite3.Connection, *, now: datetime | None = None, max_bytes: int = MAX_DB_BYTES) -> dict[str, int]:
    """Apply the retention rule (module docstring). Returns counts removed per rule."""
    now = now or datetime.now(UTC)
    removed = {"old_revisions": 0, "aged": 0, "over_budget": 0}
    with conn:
        cutoff = (now - timedelta(days=REVISION_KEEP_DAYS)).isoformat()
        ids = [r[0] for r in conn.execute("SELECT id FROM documents WHERE latest=0 AND fetched_at<?", (cutoff,))]
        _delete_ids(conn, ids)
        removed["old_revisions"] = len(ids)
        aged: list[int] = []
        for r in conn.execute("SELECT id, kind, COALESCE(NULLIF(published,''), fetched_at) AS d FROM documents"):
            if r["d"] < (now - timedelta(days=AGE_LIMIT_DAYS[_tier(r["kind"])])).isoformat():
                aged.append(r["id"])
        _delete_ids(conn, aged)
        removed["aged"] = len(aged)
    conn.execute("PRAGMA incremental_vacuum")
    target = int(max_bytes * 0.9)
    if live_bytes(conn) > max_bytes:
        order = {"news": 0, "analysis": 1, "primary": 2}
        rows = sorted(conn.execute("SELECT id, kind, COALESCE(NULLIF(published,''), fetched_at) AS d FROM documents"),
                      key=lambda r: (order[_tier(r["kind"])], r["d"]))
        batch = max(5, len(rows) // 20)
        while rows and live_bytes(conn) > target:
            chunk, rows = [r["id"] for r in rows[:batch]], rows[batch:]
            with conn:
                _delete_ids(conn, chunk)
            conn.execute("INSERT INTO docs_fts(docs_fts) VALUES ('optimize')")   # tombstones only free space once merged
            conn.execute("PRAGMA incremental_vacuum")
            removed["over_budget"] += len(chunk)
    return removed


# -- reporting -----------------------------------------------------------------------------------
def stats(conn: sqlite3.Connection) -> dict[str, Any]:
    per_source = [dict(r) for r in conn.execute(
        "SELECT source_id, kind, COUNT(*) AS docs, MAX(NULLIF(published,'')) AS newest_published, MAX(fetched_at) AS last_fetched"
        " FROM documents WHERE latest=1 GROUP BY source_id ORDER BY docs DESC")]
    feeds = [dict(r) for r in conn.execute(
        "SELECT feed_url, source_id, failures, parked_until, last_error, last_ok FROM feed_state WHERE failures>0 ORDER BY failures DESC")]
    pages = [dict(r) for r in conn.execute(
        "SELECT source_id, COUNT(*) AS failed_urls, SUM(parked) AS parked FROM page_failures GROUP BY source_id ORDER BY failed_urls DESC")]
    totals = conn.execute("SELECT COUNT(*), SUM(latest) FROM documents").fetchone()
    return {"store": str(db_path()), "db_bytes": db_path().stat().st_size if db_path().is_file() else 0,
            "live_bytes": live_bytes(conn), "budget_bytes": MAX_DB_BYTES, "documents": totals[1] or 0,
            "revisions_total": totals[0] or 0, "sources": per_source, "failing_feeds": feeds, "failing_pages": pages}
