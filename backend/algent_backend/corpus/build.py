"""
``build``: read every registered store through its adapter and bring the index up to date.

Incremental by default. Two levels of "nothing changed": a source whose store-level watermark is unchanged is not even read; a unit (a daily
file, a profile, a ledger line) whose content hash is unchanged is read but not written. A changed unit is replaced whole (its old rows deleted
by ``origin``, new rows inserted); a unit that disappeared from its store is removed. ``--since D`` considers only units dated D or later (a
quick top-up; it never deletes). ``--full`` builds a brand-new file and swaps it in, which is also the vacuum and the canonical form: an
incremental build of the same record must equal it (``tests/test_corpus_build.py``).

A source or a unit that fails is reported and skipped, never fatal: one broken store must not blind the rest (the same rule retrieval follows).
"""

from __future__ import annotations

import os
import sqlite3
import time
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from . import flags, link, paths, schema, sources
from .sink import Sink, clear_unit
from .sources.base import Source


def _now() -> str:
    return datetime.now(UTC).isoformat(timespec="seconds")


def _remove(path: Path) -> None:
    for p in (path, Path(f"{path}-wal"), Path(f"{path}-shm")):
        p.unlink(missing_ok=True)


def _run_source(db: sqlite3.Connection, src: Source, *, full: bool, since: str, now: str) -> dict[str, Any]:
    out: dict[str, Any] = {"units": 0, "changed": 0, "removed": 0, "skipped": False, "errors": [], "seconds": 0.0}
    t0 = time.perf_counter()
    mark = ""
    try:
        mark = src.watermark()
        stored = db.execute("SELECT watermark FROM source_state WHERE source = ?", (src.name,)).fetchone()
        if not full and not since and mark and stored and stored[0] == mark:
            out["skipped"] = True
            return out
        prior = {r[0]: r[1] for r in db.execute("SELECT unit, fingerprint FROM ingest_state WHERE source = ?", (src.name,))}
        seen: set[str] = set()
        db.execute("BEGIN")
        for unit in src.units():
            if since and unit.date and unit.date < since:
                seen.add(unit.key)
                continue
            seen.add(unit.key)
            out["units"] += 1
            if prior.get(unit.key) == unit.fingerprint:
                continue
            db.execute("SAVEPOINT unit")
            try:
                if unit.key in prior:
                    clear_unit(db, unit.key)
                sink = Sink(db, src.product, unit.key, now)
                unit.emit(sink)
                db.execute("INSERT OR REPLACE INTO ingest_state VALUES (?,?,?,?,?,?,?)",
                           (unit.key, src.product, src.name, unit.path, unit.date, unit.fingerprint, now))
                db.execute("RELEASE unit")
                out["changed"] += 1
            except Exception as exc:  # noqa: BLE001 - one bad unit must not lose the source
                db.execute("ROLLBACK TO unit")
                db.execute("RELEASE unit")
                out["errors"].append(f"{unit.key}: {type(exc).__name__}: {exc}")
        if not since:
            for gone in sorted(set(prior) - seen):
                clear_unit(db, gone)
                out["removed"] += 1
            db.execute("INSERT OR REPLACE INTO source_state VALUES (?,?,?)", (src.name, mark, now))
        db.execute("COMMIT")
    except Exception as exc:  # noqa: BLE001 - a store that cannot be read at all
        if db.in_transaction:
            db.execute("ROLLBACK")
        out["errors"].append(f"{src.name}: {type(exc).__name__}: {exc}")
    finally:
        out["seconds"] = round(time.perf_counter() - t0, 2)
    return out


def counts(db: sqlite3.Connection) -> dict[str, int]:
    return {t: db.execute(f"SELECT COUNT(*) FROM {t}").fetchone()[0] for t in schema.COUNTED}      # noqa: S608 - constants


def _build_into(db: sqlite3.Connection, only: list[str] | None, *, full: bool, since: str, now: str) -> dict[str, Any]:
    report: dict[str, Any] = {"sources": {}}
    for src in sources.load(only):
        report["sources"][src.name] = _run_source(db, src, full=full, since=since, now=now)
    touched = full or any(s["changed"] or s["removed"] or s["errors"] for s in report["sources"].values())
    report["touched"] = touched
    if touched:                                                # nothing changed: the link pass would reproduce what is already there
        db.execute("BEGIN")
        report["entities"], report["merge_monotone"] = link.finish(db)
        db.execute("INSERT OR REPLACE INTO meta VALUES ('built_at', ?)", (now,))
        db.execute("COMMIT")
    return report


def build(store: Path | str | None = None, *, full: bool = False, since: str = "", only: list[str] | None = None) -> dict[str, Any]:
    """Bring the index at ``store`` (default: the corpus store) up to date; returns a report (per-source units / changed / removed / errors, row counts,
    unresolved names, seconds, bytes). ``full`` rebuilds from nothing and swaps the new file in."""
    t0, now = time.perf_counter(), _now()
    target = paths.db_file(store)
    target.parent.mkdir(parents=True, exist_ok=True)
    fts = schema.fts5_available()
    if not full and target.is_file():
        probe = schema.connect(target)
        try:
            usable = schema.schema_current(probe) and schema.meta(probe, "fts") == ("fts5" if fts else "like")
        finally:
            probe.close()
        full = full or not usable
    full = full or not target.is_file()
    work = target.with_name(target.name + ".new") if full else target
    if full:
        _remove(work)
    db = schema.connect(work, write=True)
    db.isolation_level = None                                  # autocommit: transactions are explicit (a unit is a savepoint inside its source's)
    try:
        schema.create(db, fts=fts)
        report = _build_into(db, only, full=full, since=since, now=now)
        if not full and report.get("merge_monotone") is False:      # identities split: rows already folded together cannot be un-merged in place
            db.close()
            return build(store, full=True, only=only)
        report["unresolved"] = link.unresolved_count(db)
        report["rows"] = counts(db)
        if report["touched"]:
            db.execute("PRAGMA optimize")
            free = db.execute("PRAGMA freelist_count").fetchone()[0] / max(1, db.execute("PRAGMA page_count").fetchone()[0])
            if not full and free > flags.VACUUM_FREE_SHARE:
                db.execute("VACUUM")
                report["vacuumed"] = True
        db.execute("PRAGMA wal_checkpoint(TRUNCATE)")
    finally:
        db.close()
    if full:
        _remove(Path(f"{target}-wal"))
        _remove(Path(f"{target}-shm"))
        os.replace(work, target)
        _remove(Path(f"{work}-wal"))
        _remove(Path(f"{work}-shm"))
    report.update(full=full, since=since, seconds=round(time.perf_counter() - t0, 2), bytes=target.stat().st_size, path=str(target))
    report["errors"] = [e for s in report["sources"].values() for e in s["errors"]]
    return report
