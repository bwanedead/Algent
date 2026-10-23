"""
``newsroom site`` - checks of the deployed site (docs/guides/deploy.md).

    newsroom site smoke [--base URL] [--json] [--log]     request every registered route, a sample of dynamic pages and the agent API; exit 1 on any failure

``--base`` defaults to production (ops/smoke/flags.PRODUCTION_BASE); pass a preview URL to check a deployment before promoting it. ``--log`` (what the hourly
``site-smoke`` job passes) keeps the report for the doctor row and writes ~/ops-log.md on failures and recoveries; a run against any other base never does.
Free; no model; about 60 paced requests.
"""

from __future__ import annotations

import json
from typing import Any


def add_parser(sub: Any) -> None:
    p = sub.add_parser("site", help="checks of the deployed site: smoke test of every route and the agent API")
    verbs = p.add_subparsers(dest="site_cmd", required=True)
    s = verbs.add_parser("smoke", help="request the site's routes and judge the answers")
    s.add_argument("--base", default="", help="site origin to check (default: production)")
    s.add_argument("--json", action="store_true", help="the full report as JSON")
    s.add_argument("--log", action="store_true", help="record the result for the doctor and write ~/ops-log.md on failure/recovery (production only)")
    s.set_defaults(handler=run_smoke)


def run_smoke(args: Any) -> int:
    from algent_backend.ops.smoke import flags, run, state

    try:
        report = run.run(args.base or None)
    except ValueError as exc:
        print(str(exc))
        return 2
    if args.log and report.base == flags.PRODUCTION_BASE:
        state.record(report)
    print(json.dumps(report.as_dict(), indent=2, ensure_ascii=False) if args.json else report.text())
    return 0 if report.ok else 1
