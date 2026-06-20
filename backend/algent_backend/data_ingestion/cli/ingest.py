"""
``ingest`` — fetch the latest source batch, build its digest, write it to disk.

CLI-initiated for now (a scheduler will drive it later). One run = one batch =
one digest file. Prints a single JSON summary; the full digest goes to
``ingestion_data/digests/<source>_<batch_id>.json``.

    python -m algent_backend.data_ingestion.cli ingest
    python -m algent_backend.data_ingestion.cli ingest --source gdelt_gkg
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

from ..news_production.discovery.digest import build_digest
from ..news_production.sources import gdelt_gkg

# backend/ — parents: [cli, data_ingestion, algent_backend, backend]
_BACKEND_DIR = Path(__file__).resolve().parents[3]
_OUTPUT_ENV = "ALGENT_INGESTION_DIR"

# Registered sources: id -> zero-arg fetcher returning (batch_id, records).
_SOURCES = {"gdelt_gkg": gdelt_gkg.fetch_latest}


def add_parser(subparsers: argparse._SubParsersAction) -> None:
    parser = subparsers.add_parser("ingest", help="fetch a source batch and write its digest")
    parser.add_argument("--source", default="gdelt_gkg", choices=sorted(_SOURCES))
    parser.set_defaults(handler=run)


def run(args: argparse.Namespace) -> int:
    fetch = _SOURCES[args.source]
    batch_id, records = fetch()
    digest = build_digest(records, source=args.source, batch_id=batch_id)

    path = _digests_dir() / f"{args.source}_{batch_id}.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(digest.model_dump_json(indent=2), encoding="utf-8")

    _print_json(
        {
            "source": args.source,
            "batch_id": batch_id,
            "total_records": digest.total_records,
            "languages": len(digest.languages),
            "digest_path": str(path),
        }
    )
    return 0


def _digests_dir() -> Path:
    override = os.environ.get(_OUTPUT_ENV)
    base = Path(override) if override else _BACKEND_DIR / "ingestion_data"
    return base / "digests"


def _print_json(payload: object) -> None:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    json.dump(payload, sys.stdout, ensure_ascii=False, indent=2, default=str)
    sys.stdout.write("\n")
