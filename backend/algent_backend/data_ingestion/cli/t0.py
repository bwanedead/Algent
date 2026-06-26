"""
``t0`` — produce the t0 discovery pool from its toggleable source channels.

This is the one command that *builds* a t0 end to end (the ``pool`` command only
consolidates already-written artifacts). It runs the same ``ensure_t0`` the
discovery agent self-runs, so you can test t0 — and each individual channel — by
hand, picking which sources to spend on.

Channels: ``gkg`` (free GDELT net), ``beats`` (DOC sweep from disk), ``markets``
(Polymarket), ``x`` (Grok CLI — slow, spends subscription quota). X is off by
default; opt in explicitly. Progress prints to stderr; one JSON summary to stdout.

    python -m algent_backend.cli ingest t0                      # default channels
    python -m algent_backend.cli ingest t0 --channels gkg,x     # just GKG + X
    python -m algent_backend.cli ingest t0 --channels x --force # test X alone
"""

from __future__ import annotations

import argparse

from ..news_production.discovery.pipeline import (
    ALL_CHANNELS,
    DEFAULT_FRESH_MINUTES,
    ensure_t0,
    resolve_channels,
)
from ._shared import print_json, progress


def add_parser(subparsers: argparse._SubParsersAction) -> None:
    parser = subparsers.add_parser("t0", help="build the t0 discovery pool (toggleable channels)")
    parser.add_argument(
        "--channels",
        help=f"comma list of {','.join(ALL_CHANNELS)} (default: env ALGENT_T0_CHANNELS or gkg,beats,markets)",
    )
    parser.add_argument(
        "--force", action="store_true",
        help="rebuild even if a fresh pool exists (sets fresh-minutes to 0)",
    )
    parser.set_defaults(handler=run)


def run(args: argparse.Namespace) -> int:
    channels = set(args.channels.split(",")) if args.channels else None
    chans = resolve_channels(channels)
    progress(f"[t0] building with channels: {', '.join(sorted(chans))}")

    pool, path = ensure_t0(
        channels=chans,
        fresh_minutes=0 if args.force else DEFAULT_FRESH_MINUTES,
        on_progress=progress,
    )
    print_json({
        "channels": sorted(chans),
        "item_count": pool.get("item_count"),
        "by_channel": pool.get("by_channel"),
        "by_pillar": pool.get("by_pillar"),
        "pool_path": path,
    })
    return 0
