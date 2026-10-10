"""
``newsroom reads`` — which page-reading rung actually rescues pages?

    newsroom reads [--days 7]

One JSON document from ``runs_data/read_ledger.jsonl``: share of good reads by final rung, failure
rate, top failing domains, and how many reads only Firecrawl/Playwright rescued (the evidence for
whether installing Playwright pays off). ``newsroom search-usage`` is the same for web searches
(``search/search_ledger.py``). See ``tools/sourcing/depth/read_ledger.py``.
"""

from __future__ import annotations

import json
from typing import Any

from algent_backend.agent_system.tools.sourcing.depth import read_ledger


def add_parser(sub: Any) -> None:
    p = sub.add_parser("reads", help="summarise the page-read ledger: which rung rescues what")
    p.add_argument("--days", type=int, default=7)
    p.set_defaults(handler=run_reads)
    u = sub.add_parser("search-usage", help="summarise the search ledger: who answers, free vs paid, failures")
    u.add_argument("--days", type=int, default=7)
    u.set_defaults(handler=run_search_usage)


def run_reads(args: Any) -> int:
    from algent_backend.agent_system.tools.sourcing.search import quota

    print(json.dumps({**read_ledger.summarise(args.days), "paid_this_month": quota.summary()}, indent=2))
    return 0


def run_search_usage(args: Any) -> int:
    from algent_backend.agent_system.tools.sourcing.search import search_ledger

    print(json.dumps(search_ledger.summarise(args.days), indent=2))
    return 0
