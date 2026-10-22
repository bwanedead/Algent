"""
``newsroom publish`` - republish what the site reads from the server's local stores (docs/architecture/database-budget.md, runbook).

    newsroom publish rebuild-all [--dry-run] [--only STEP[,STEP]]

Builds every document the site reads (dailies and dossiers, articles and images, live / maritime / sanctions / calendar / geoledger products,
track record, benchmarks, satellite) from the local stores and sends the ones whose content hash is not already recorded. Idempotent: a re-run
sends only what is missing or changed. ``--dry-run`` builds everything and prints how many documents would be sent (an estimate of the Class A
operations the run costs); it sends and records nothing. Prints one JSON document; exit 1 when any step failed.
"""

from __future__ import annotations

import json
from typing import Any


def add_parser(sub: Any) -> None:
    p = sub.add_parser("publish", help="republish everything the site reads from the local stores (rebuild-all)")
    verbs = p.add_subparsers(dest="publish_cmd", required=True)
    r = verbs.add_parser("rebuild-all", help="rebuild and publish every document (idempotent, hash-skipping)")
    r.add_argument("--dry-run", action="store_true", help="build and count; send nothing")
    r.add_argument("--only", default="", help="comma-separated steps: site-documents, articles, images, live, maritime, sanctions, calendar, geoledger, markets, ai-benchmarks, satellite")
    r.set_defaults(handler=run_rebuild_all)


def run_rebuild_all(args: Any) -> int:
    from algent_backend.publishing import rebuild

    only = [s.strip() for s in args.only.split(",") if s.strip()]
    report = rebuild.run(dry_run=args.dry_run, only=only or None)
    print(json.dumps(report, indent=2, ensure_ascii=False))
    return 0 if report["ok"] else 1
