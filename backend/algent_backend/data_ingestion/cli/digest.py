"""
``digest`` — run a source's processing pipeline into a :class:`DiscoveryDigest`.

This is the processing step (distinct from raw ``fetch``): it fetches the latest
batch, parses it, and computes the multi-lens, per-language stats digest a
discovery agent reads. Only sources with a digest pipeline are offered; today
that is GKG. The full digest is written to ``ingestion_data/digests/``.

    python -m algent_backend.data_ingestion.cli digest gdelt_gkg
"""

from __future__ import annotations

import argparse

from ..news_production.discovery.digest import build_digest
from ..news_production.sources import gdelt_gkg
from ._shared import DIGESTABLE, digests_dir, print_json

# Each digestable source: id -> (fetch latest -> (batch_id, records)).
_FETCHERS = {gdelt_gkg.SOURCE_ID: gdelt_gkg.fetch_latest}


def add_parser(subparsers: argparse._SubParsersAction) -> None:
    parser = subparsers.add_parser("digest", help="process a source's latest batch into a digest")
    parser.add_argument("source", choices=sorted(DIGESTABLE))
    parser.set_defaults(handler=run)


def run(args: argparse.Namespace) -> int:
    batch_id, records = _FETCHERS[args.source]()
    digest = build_digest(records, source=args.source, batch_id=batch_id)

    path = digests_dir() / f"{args.source}_{batch_id}.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(digest.model_dump_json(indent=2), encoding="utf-8")

    print_json(
        {
            "source": args.source,
            "batch_id": batch_id,
            "total_records": digest.total_records,
            "languages": len(digest.languages),
            "digest_path": str(path),
        }
    )
    return 0
