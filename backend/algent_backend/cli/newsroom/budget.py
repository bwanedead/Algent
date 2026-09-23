"""
``newsroom budget`` — the spend envelope that caps unattended work across runs.

    newsroom budget open --usd 5 --runs 5 --note "overnight"
    newsroom budget status
    newsroom budget close

While an envelope is open, every article run claims from it and is capped at what is left;
an exhausted envelope refuses new runs before they spend. See
``agent_system/foundation/spend_budget.py``.
"""

from __future__ import annotations

import json
from typing import Any

from algent_backend.agent_system.foundation import spend_budget as sb


def add_parser(sub: Any) -> None:
    p = sub.add_parser("budget", help="cap total spend and run count across unattended runs")
    verbs = p.add_subparsers(dest="budget_cmd", required=True)
    o = verbs.add_parser("open", help="open an envelope (replaces any current one)")
    o.add_argument("--usd", type=float, required=True)
    o.add_argument("--runs", type=int, required=True)
    o.add_argument("--note", default="")
    o.set_defaults(handler=run_open)
    verbs.add_parser("status", help="spent, reserved and left").set_defaults(handler=run_status)
    verbs.add_parser("close", help="remove the envelope").set_defaults(handler=run_close)


def run_open(args: Any) -> int:
    sb.open_envelope(args.usd, args.runs, note=args.note)
    return run_status(args)


def run_status(_args: Any) -> int:
    sb.reconcile()
    state = sb.load()
    if state is None:
        print(json.dumps({"envelope": None, "note": "no envelope open — runs are capped per article only"}))
        return 0
    print(json.dumps({
        "limit_usd": state["limit_usd"], "committed_usd": sb.committed(state),
        "left_usd": sb.remaining(state), "runs_used": sb.runs_used(state),
        "max_runs": state["max_runs"], "note": state.get("note", ""),
        "entries": state.get("entries", []),
    }, indent=2))
    return 0


def run_close(_args: Any) -> int:
    sb.close_envelope()
    print(json.dumps({"envelope": None, "note": "closed"}))
    return 0
