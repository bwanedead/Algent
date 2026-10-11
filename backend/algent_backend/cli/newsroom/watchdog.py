"""
``newsroom watchdog`` — one pass of the runaway-bill guard; spends nothing.

    newsroom watchdog [--dry-run]     stop paid runs over their time/spend limits
    newsroom watchdog --clear-halt    lift today's spend halt

Run every 2 minutes by the ``ohmega-watchdog`` timer. Limits: ``ops/flags.py``. See ``ops/watchdog.py``.
"""

from __future__ import annotations

import json
from typing import Any


def add_parser(sub: Any) -> None:
    p = sub.add_parser("watchdog", help="stop paid runs that run too long or spend too much (one pass)")
    p.add_argument("--dry-run", action="store_true", help="log what would be killed; kill nothing")
    p.add_argument("--clear-halt", action="store_true", help="remove today's spend-halt marker")
    p.set_defaults(handler=run_watchdog)


def run_watchdog(args: Any) -> int:
    from algent_backend.ops import watchdog

    if args.clear_halt:
        print(json.dumps({"halt_cleared": watchdog.clear_halt()}))
        return 0
    watchdog.run_pass(dry_run=args.dry_run)
    return 0
