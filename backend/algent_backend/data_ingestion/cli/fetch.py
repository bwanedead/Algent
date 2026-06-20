"""
``fetch`` — the contact/initiation surface: retrieve + unpack the latest packet.

Retrieves exactly one (the newest) batch of a source, unpacks it, and lands each
part verbatim under ``ingestion_data/raw/<source>/<batch_id>/``. No processing —
this is the "can we reliably contact and unpack it" surface, so we can look at
real data and then decide what to process it for.

    python -m algent_backend.data_ingestion.cli fetch gdelt_gkg
    python -m algent_backend.data_ingestion.cli fetch gdelt_ngrams
"""

from __future__ import annotations

import argparse

from ._shared import SOURCES, print_json, prune_raw_batches, raw_dir


def add_parser(subparsers: argparse._SubParsersAction) -> None:
    parser = subparsers.add_parser("fetch", help="retrieve + unpack a source's latest packet")
    parser.add_argument("source", choices=sorted(SOURCES))
    parser.add_argument(
        "--keep",
        type=int,
        default=1,
        help="raw batches to retain for this source (default 1 = one-in-one-out)",
    )
    parser.set_defaults(handler=run)


def run(args: argparse.Namespace) -> int:
    packet = SOURCES[args.source].fetch_latest_raw()

    out_dir = raw_dir() / packet.source / packet.batch_id
    out_dir.mkdir(parents=True, exist_ok=True)
    parts_summary = []
    for part in packet.parts:
        path = out_dir / part.name
        path.write_text(part.text, encoding="utf-8")
        parts_summary.append(
            {"name": part.name, "records": part.record_count, "bytes": path.stat().st_size}
        )

    purged = prune_raw_batches(packet.source, keep=args.keep)
    print_json(
        {
            "source": packet.source,
            "batch_id": packet.batch_id,
            "parts": parts_summary,
            "raw_dir": str(out_dir),
            "retained": args.keep,
            "purged": purged,
        }
    )
    return 0
