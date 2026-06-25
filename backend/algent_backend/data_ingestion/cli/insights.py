"""
``insights`` — the deterministic discovery artifact for a source's latest batch.

Fetches the batch, builds a ranked candidate list (themes + entities) carrying
velocity / cross-language / novelty / tone signals against the rolling memory,
and writes an :class:`InsightsReport`. Nothing raw is retained: the batch streams
through memory and is dropped; only the small report and the rolling state stay.

Memory is updated only after a successful build, so a failure never corrupts the
baselines.

    python -m algent_backend.data_ingestion.cli insights gdelt_gkg
    python -m algent_backend.data_ingestion.cli insights gdelt_gkg --warmup 8   # bootstrap
"""

from __future__ import annotations

import argparse
from datetime import UTC, datetime, timedelta

from ..news_production.discovery.candidates import extract_candidates
from ..news_production.discovery.insights import build_insights
from ..news_production.discovery.memory import RollingMemory, load_memory, save_memory
from ..news_production.sources import gdelt_gkg
from ._shared import DIGESTABLE, insights_dir, memory_dir, print_json, progress, prune_files

# Sources with a deterministic insights pipeline. id -> fetch -> (batch_id, records).
_FETCHERS = {gdelt_gkg.SOURCE_ID: gdelt_gkg.fetch_latest}
# Sources that can fetch a specific historical batch (for cold-start warmup).
_BATCH_FETCHERS = {gdelt_gkg.SOURCE_ID: gdelt_gkg.fetch_batch}


def add_parser(subparsers: argparse._SubParsersAction) -> None:
    parser = subparsers.add_parser("insights", help="build the deterministic discovery report")
    parser.add_argument("source", choices=sorted(DIGESTABLE))
    parser.add_argument(
        "--keep",
        type=int,
        default=1,
        help="insight reports to retain for this source (default 1)",
    )
    parser.add_argument(
        "--warmup",
        type=int,
        default=0,
        help="backfill memory from N preceding batches first (bootstrap velocity on run 1)",
    )
    parser.set_defaults(handler=run)


def run(args: argparse.Namespace) -> int:
    progress(f"[insights] fetching latest {args.source} batch (downloads)…")
    batch_id, records = _FETCHERS[args.source]()
    progress(f"[insights] batch {batch_id}: {len(records)} records")

    memory = load_memory(args.source, memory_dir())
    warmed: list[str] = []
    if args.warmup:
        memory, warmed = _warm_memory(args.source, batch_id, args.warmup, memory)
    progress("[insights] building digest…")
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
            "warmed_batches": len(warmed),
            "report_path": str(path),
            "retained": args.keep,
            "purged": purged,
        }
    )
    return 0


def _preceding_batch_ids(batch_id: str, n: int) -> list[str]:
    """The n 15-minute batch stamps immediately before ``batch_id``, oldest first."""
    dt = datetime.strptime(batch_id, "%Y%m%d%H%M%S").replace(tzinfo=UTC)
    ids = [(dt - timedelta(minutes=15 * (i + 1))).strftime("%Y%m%d%H%M%S") for i in range(n)]
    return list(reversed(ids))


def _warm_memory(
    source: str, batch_id: str, n: int, memory: RollingMemory
) -> tuple[RollingMemory, list[str]]:
    """Fold the counts of the N preceding historical batches into memory.

    Best-effort: a batch that fails to download is skipped, not fatal.
    """
    fetch = _BATCH_FETCHERS.get(source)
    if fetch is None:
        return memory, []
    ids = _preceding_batch_ids(batch_id, n)
    progress(f"[insights] warming velocity from {len(ids)} prior batches (downloads)…")
    warmed: list[str] = []
    for i, bid in enumerate(ids, 1):
        try:
            _, records = fetch(bid)
        except Exception:
            progress(f"[insights] warmup {i}/{len(ids)}  {bid} -> skipped (fetch failed)")
            continue
        counts = {s.full_key: s.count for s in extract_candidates(records)}
        memory = memory.with_batch(bid, counts)
        warmed.append(bid)
        progress(f"[insights] warmup {i}/{len(ids)}  {bid} -> {len(records)} records")
    return memory, warmed
