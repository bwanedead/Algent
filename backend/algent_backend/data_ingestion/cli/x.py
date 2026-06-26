"""
``x`` — X discovery A/B harness: the Grok CLI (subscription) vs the native X API.

Run each side, eyeball the hits + count, and (for native) watch the cost. Lets us
settle which X channel is better juice-per-spend before wiring it into t0.

    python -m algent_backend.cli ingest x --via grok      # subscription CLI (free-ish)
    python -m algent_backend.cli ingest x --via native    # X API (paid per post)
"""

from __future__ import annotations

import argparse
from pathlib import Path

from ._shared import print_json, progress


def add_parser(subparsers: argparse._SubParsersAction) -> None:
    parser = subparsers.add_parser("x", help="X discovery A/B: grok CLI vs native API")
    parser.add_argument("--via", choices=["grok", "native"], required=True)
    parser.add_argument("--limit", type=int, default=20)
    parser.set_defaults(handler=run)


def run(args: argparse.Namespace) -> int:
    # Load backend/.env so the native path sees X_BEARER_KEY (grok scrubs keys anyway).
    from algent_backend.config.env_file import load_env_file

    load_env_file(Path(__file__).resolve().parents[3] / ".env")
    progress(f"[x] discovering via {args.via}…")
    if args.via == "grok":
        from ..newsroom.sources.x_grok_cli import fetch_x_grok

        hits = fetch_x_grok(limit=args.limit)
    else:
        from ..newsroom.sources.x_native import fetch_x_native

        hits = fetch_x_native(limit=args.limit)

    print_json({"via": args.via, "count": len(hits), "hits": hits})
    return 0
