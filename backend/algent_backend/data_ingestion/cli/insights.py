"""
``insights`` — the deterministic discovery artifact for a source's latest batch.

Fetches the batch, builds a ranked candidate list (themes + entities) carrying
velocity / cross-language / novelty / tone signals against the rolling memory,
and writes an :class:`InsightsReport`. Nothing raw is retained: the batch streams
through memory and is dropped; only the small report and the rolling state stay.

Memory is updated only after a successful build, so a failure never corrupts the
baselines.

    python -m algent_backend.data_ingestion.cli insights gdelt_gkg
"""

from __future__ import annotations

import argparse

from ..news_production.discovery.insights import build_insights
from ..news_production.discovery.memory import load_memory, save_memory
from ..news_production.sources import gdelt_gkg
from ._shared import DIGESTABLE, insights_dir, memory_dir, print_json, prune_files

# Sources with a deterministic insights pipeline. id -> fetch -> (batch_id, records).
_FETCHERS = {gdelt_gkg.SOURCE_ID: gdelt_gkg.fetch_latest}


def add_parser(subparsers: argparse._SubParsersAction) -> None:
    parser = subparsers.add_parser("insights", help="build the deterministic discovery report")
    parser.add_argument("source", choices=sorted(DIGESTABLE))
    parser.add_argument(
        "--keep",
        type=int,
        default=1,
        help="insight reports to retain for this source (default 1)",
    )
    parser.set_defaults(handler=run)


def run(args: argparse.Namespace) -> int:
    batch_id, records = _FETCHERS[args.source]()

    memory = load_memory(args.source, memory_dir())
    report, counts = build_insights(records, source=args.source, batch_id=batch_id, memory=memory)

    out_dir = insights_dir()
    out_dir.mkdir(parents=True, exist_ok=True)
    path = out_dir / f"{args.source}_{batch_id}.json"
    path.write_text(report.model_dump_json(indent=2), encoding="utf-8")

    # Persist state only now that the report is safely written.
    save_memory(memory.with_batch(batch_id, counts), memory_dir())
    purged = prune_files(out_dir, f"{args.source}_*.json", keep=args.keep)

    print_json(
        {
            "source": args.source,
            "batch_id": batch_id,
            "total_records": report.total_records,
            "candidates": len(report.candidates),
            "rising": sum(1 for c in report.candidates if c.rising),
            "novel": sum(1 for c in report.candidates if c.novel),
            "has_velocity_baseline": report.has_velocity_baseline,
            "languages": len(report.by_language),
            "report_path": str(path),
            "retained": args.keep,
            "purged": purged,
        }
    )
    return 0
