"""
``newsroom db`` — keep the free-plan Postgres under its 500 MB quota (docs/architecture/database-budget.md). Spends nothing.

    newsroom db size                          database size vs the quota, biggest tables, dead-row ratio, WAL when visible
    newsroom db prune [--apply]               retention windows from database/flags.py; dry run unless --apply (the daily timer applies)
    newsroom db diet [--apply]                recovery one-shot: move inline document bodies to Storage, prune, vacuum (idempotent)
    newsroom db vacuum-full [--apply]         VACUUM FULL the bloated tables, smallest first (after the diet; needs disk headroom)

Every command prints one JSON document. ``--dry-run`` is the default and is accepted for clarity.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any


def add_parser(sub: Any) -> None:
    p = sub.add_parser("db", help="database size budget: size, prune, diet (recovery), vacuum-full")
    verbs = p.add_subparsers(dest="db_cmd", required=True)
    verbs.add_parser("size", help="size vs quota, top tables, dead rows, WAL").set_defaults(handler=run_size)
    for name, handler, text in (("prune", run_prune, "apply the retention windows"),
                                ("diet", run_diet, "move inline documents to Storage, prune, vacuum"),
                                ("vacuum-full", run_vacuum_full, "VACUUM FULL the bloated tables, smallest first")):
        v = verbs.add_parser(name, help=text)
        mode = v.add_mutually_exclusive_group()
        mode.add_argument("--apply", action="store_true", help="do it (default is a dry run that changes nothing)")
        mode.add_argument("--dry-run", action="store_true", help="print what would happen (the default)")
        v.set_defaults(handler=handler)


def _env() -> None:
    try:
        from dotenv import load_dotenv

        load_dotenv(Path(__file__).resolve().parents[3] / ".env")
    except ImportError:
        pass


def _emit(doc: Any) -> int:
    print(json.dumps(doc, indent=2, ensure_ascii=False))
    return 0


def _connect():
    from algent_backend.database.migrate import connect  # the package re-exports a function named `migrate`

    return connect()


def run_size(_args: Any) -> int:
    from algent_backend.database import size

    _env()
    with _connect() as conn:
        rep = size.report(conn)
    rep["summary"] = size.summary_line(rep)
    _emit(rep)
    return 1 if rep["status"] == size.FAIL else 0


def run_prune(args: Any) -> int:
    from algent_backend.database import prune

    _env()
    with _connect() as conn:
        return _emit(prune.run(conn, apply=args.apply))


def run_diet(args: Any) -> int:
    from algent_backend.database import diet

    _env()
    with _connect() as conn:
        return _emit(diet.run(conn, apply=args.apply))


def run_vacuum_full(args: Any) -> int:
    from algent_backend.database import diet

    _env()
    with _connect() as conn:
        return _emit(diet.vacuum_full(conn, apply=args.apply))
