"""
``x`` — X discovery probe: **News + general aggregators** (default t0) vs Grok / raw search.

    python -m algent_backend.cli ingest x --via api      # News stories + MarioNawfal-class wires
    python -m algent_backend.cli ingest x --via native  # one news/search or speech-act search
    python -m algent_backend.cli ingest x --via grok    # optional Grok Build supplement
"""

from __future__ import annotations

import argparse
from pathlib import Path

from ._shared import print_json, progress


def add_parser(subparsers: argparse._SubParsersAction) -> None:
    parser = subparsers.add_parser("x", help="X discovery: News stories (primary) or Grok")
    parser.add_argument("--via", choices=["api", "native", "grok"], default="api")
    parser.add_argument("--limit", type=int, default=20, help="max stories/hits")
    parser.set_defaults(handler=run)


def run(args: argparse.Namespace) -> int:
    from algent_backend.config.env_file import load_env_file

    load_env_file(Path(__file__).resolve().parents[3] / ".env")
    progress(f"[x] discovering via {args.via}…")
    cost: dict = {}
    if args.via == "grok":
        from ..newsroom.sources.x_grok_cli import fetch_x_grok

        hits = fetch_x_grok(limit=min(args.limit, 10))
    elif args.via == "api":
        from ..newsroom.sources.x_native import fetch_x_api_discovery, last_cost

        # max_posts left to env/default so aggregators (timelines) can run.
        hits = fetch_x_api_discovery(max_stories=args.limit)
        cost = last_cost()
    else:
        from ..newsroom.sources.x_native import fetch_x_native, last_cost

        hits = fetch_x_native(limit=args.limit)
        cost = last_cost()

    print_json({"via": args.via, "count": len(hits), "cost": cost, "hits": hits[:40]})
    return 0
