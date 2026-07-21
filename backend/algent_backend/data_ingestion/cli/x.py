"""
``x`` — X discovery probe: **sparse trends API** (default t0) vs optional Grok / post search.

    python -m algent_backend.cli ingest x --via api      # WW+US trends, ≤30 topics, $0 posts default
    python -m algent_backend.cli ingest x --via native  # single recent-search (costs posts)
    python -m algent_backend.cli ingest x --via grok    # optional Grok Build supplement
"""

from __future__ import annotations

import argparse
from pathlib import Path

from ._shared import print_json, progress


def add_parser(subparsers: argparse._SubParsersAction) -> None:
    parser = subparsers.add_parser("x", help="X discovery: sparse trends API (primary) or Grok")
    parser.add_argument("--via", choices=["api", "native", "grok"], default="api")
    parser.add_argument("--limit", type=int, default=30, help="max topics (api) or posts (native)")
    parser.set_defaults(handler=run)


def run(args: argparse.Namespace) -> int:
    # Load backend/.env so the API path sees X_BEARER_TOKEN / X_BEARER_KEY.
    from algent_backend.config.env_file import load_env_file

    load_env_file(Path(__file__).resolve().parents[3] / ".env")
    progress(f"[x] discovering via {args.via}…")
    cost: dict = {}
    if args.via == "grok":
        from ..newsroom.sources.x_grok_cli import fetch_x_grok

        hits = fetch_x_grok(limit=min(args.limit, 10))
    elif args.via == "api":
        from ..newsroom.sources.x_native import fetch_x_api_discovery, last_cost

        hits = fetch_x_api_discovery(max_topics=args.limit)
        cost = last_cost()
    else:
        from ..newsroom.sources.x_native import fetch_x_native, last_cost

        hits = fetch_x_native(limit=args.limit)
        cost = last_cost()

    print_json({"via": args.via, "count": len(hits), "cost": cost, "hits": hits[:40]})
    return 0
