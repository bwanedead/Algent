"""
Schema migrations — the database is rebuilt from ``backend/migrations/*.sql``, never by hand.

Files are applied in name order (``001_…``, ``002_…``), each in its own transaction, and recorded
in ``schema_migrations`` so a migration runs exactly once. A failed migration rolls back whole and
stops the run: a half-applied schema is worse than an unapplied one.

    python -m algent_backend.database status
    python -m algent_backend.database migrate

The connection string comes from ``DATABASE_URL`` (backend/.env). The driver (psycopg) is imported
only when a connection is actually made, so the rest of the codebase — and its tests — never need it.
"""

from __future__ import annotations

import os
from pathlib import Path

MIGRATIONS_DIR = Path(__file__).resolve().parents[2] / "migrations"
_LEDGER = """
create table if not exists schema_migrations (
    version     text primary key,
    applied_at  timestamptz not null default now()
)
"""


def available(folder: Path = MIGRATIONS_DIR) -> list[Path]:
    return sorted(folder.glob("[0-9][0-9][0-9]_*.sql"))


def pending(applied: set[str], folder: Path = MIGRATIONS_DIR) -> list[Path]:
    """Migrations not yet applied, in order. Refuses a gap: 003 must not run before 002."""
    files = available(folder)
    out = [f for f in files if f.stem not in applied]
    first_pending = files.index(out[0]) if out else len(files)
    late = [f.stem for f in files[first_pending:] if f.stem in applied]
    if late:
        raise RuntimeError(f"migrations applied out of order after {files[first_pending].stem}: {late}")
    return out


def database_url() -> str:
    url = os.environ.get("DATABASE_URL", "")
    if not url:
        try:
            from dotenv import load_dotenv

            load_dotenv(Path(__file__).resolve().parents[2] / ".env")
        except ImportError:
            pass
        url = os.environ.get("DATABASE_URL", "")
    if not url:
        raise RuntimeError("DATABASE_URL is not set (backend/.env) — see docs/architecture/pulse-system.md")
    return url


def connect():
    import psycopg   # imported here on purpose: only a real connection needs the driver

    return psycopg.connect(database_url())


def applied_versions(conn) -> set[str]:
    with conn.cursor() as cur:
        cur.execute(_LEDGER)
        cur.execute("select version from schema_migrations")
        return {row[0] for row in cur.fetchall()}


def migrate() -> list[str]:
    """Apply every pending migration. Returns the versions applied."""
    done: list[str] = []
    with connect() as conn:
        todo = pending(applied_versions(conn))
        conn.commit()
        for path in todo:
            with conn.transaction():
                with conn.cursor() as cur:
                    cur.execute(path.read_text(encoding="utf-8"))
                    cur.execute("insert into schema_migrations(version) values (%s)", (path.stem,))
            done.append(path.stem)
    return done


def status() -> dict:
    with connect() as conn:
        applied = applied_versions(conn)
    return {"applied": sorted(applied), "pending": [p.stem for p in pending(applied)]}
