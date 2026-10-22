"""
``newsroom storage`` - the R2 free-tier budget (docs/architecture/database-budget.md, "R2 budget"). Spends nothing, makes no request.

    newsroom storage status        month-to-date Class A / Class B operations and stored bytes, today's use against the daily
                                   allowance, the projection to the end of the month, and the warn (70%) / hard-stop (90%) levels

Prints one JSON document; exit code 1 at the hard stop (writes are being refused).
"""

from __future__ import annotations

import json
from typing import Any


def add_parser(sub: Any) -> None:
    p = sub.add_parser("storage", help="R2 free-tier budget: month-to-date operations, bytes, projections")
    verbs = p.add_subparsers(dest="storage_cmd", required=True)
    verbs.add_parser("status", help="usage vs the free tier, projections, hard-stop state").set_defaults(handler=run_status)


def run_status(_args: Any) -> int:
    from algent_backend.publishing import object_budget, object_store

    rep = object_budget.meter().status()
    store = object_store.select(allow_unconfigured=True)
    rep["backend"] = store.name if store else "none"
    rep["configured"] = object_store.configured()
    rep["public_base"] = object_store.public_base()
    print(json.dumps(rep, indent=2))
    return 1 if rep["level"] == "stop" else 0
