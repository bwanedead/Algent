"""
``pool`` — consolidate the latest GKG insights + beat sheet into one candidate pool.

Leg 1 of the funnel: reads the most recent ``insights`` report and ``beats`` sheet
from disk and folds them into a single grounded, tagged :class:`DiscoveryPool` —
the input tray the synthesis (discovery) agent will read. Deterministic; no LLM.

Run ``insights`` and ``sweep`` first; this just consolidates their artifacts.

    python -m algent_backend.data_ingestion.cli pool
"""

from __future__ import annotations

import argparse
from datetime import UTC, datetime

from ..newsroom.discovery.pool import build_pool
from ..newsroom.discovery.report import BeatSheet, InsightsReport
from ._shared import (
    beats_dir,
    insights_dir,
    latest_file,
    pool_dir,
    print_json,
    prune_files,
)


def add_parser(subparsers: argparse._SubParsersAction) -> None:
    parser = subparsers.add_parser("pool", help="consolidate latest insights + beats into a pool")
    parser.add_argument("--source", default="gdelt_gkg", help="insights source id to read")
    parser.add_argument("--keep", type=int, default=1, help="pools to retain (default 1)")
    parser.set_defaults(handler=run)


def run(args: argparse.Namespace) -> int:
    insights = _load(latest_file(insights_dir(), f"{args.source}_*.json"), InsightsReport)
    sheet = _load(latest_file(beats_dir(), "beats_*.json"), BeatSheet)
    if insights is None and sheet is None:
        print_json({"error": "no insights or beat artifacts found; run insights/sweep first"})
        return 1

    pool = build_pool(insights, sheet)

    stamp = datetime.now(UTC).strftime("%Y%m%d%H%M%S")
    out_dir = pool_dir()
    out_dir.mkdir(parents=True, exist_ok=True)
    path = out_dir / f"pool_{stamp}.json"
    path.write_text(pool.model_dump_json(indent=2), encoding="utf-8")
    purged = prune_files(out_dir, "pool_*.json", keep=args.keep)

    print_json(
        {
            "item_count": pool.item_count,
            "by_channel": pool.by_channel,
            "by_pillar": pool.by_pillar,
            "gkg_batch_id": pool.gkg_batch_id,
            "pool_path": str(path),
            "retained": args.keep,
            "purged": purged,
        }
    )
    return 0


def _load(path, model):
    if path is None:
        return None
    return model.model_validate_json(path.read_text(encoding="utf-8"))
