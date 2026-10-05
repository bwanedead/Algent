"""
``newsroom reads`` — which page-reading rung actually rescues pages?

    newsroom reads [--days 7]

One JSON document from ``runs_data/read_ledger.jsonl``: share of good reads by final rung, failure
rate, top failing domains, and how many reads only Firecrawl/Playwright rescued (the evidence for
whether installing Playwright pays off). See ``tools/sourcing/depth/read_ledger.py``.
"""

from __future__ import annotations

import json
from typing import Any

from algent_backend.agent_system.tools.sourcing.depth import read_ledger


def add_parser(sub: Any) -> None:
    p = sub.add_parser("reads", help="summarise the page-read ledger: which rung rescues what")
    p.add_argument("--days", type=int, default=7)
    p.set_defaults(handler=run_reads)


def run_reads(args: Any) -> int:
    print(json.dumps(read_ledger.summarise(args.days), indent=2))
    return 0
