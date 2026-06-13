"""``list`` — the cross-run ledger, newest first."""

from __future__ import annotations

import argparse

from algent_backend.agent_system.runs.control_plane.ledger import RunLedger

from ._shared import print_json


def add_parser(subparsers: argparse._SubParsersAction) -> None:
    parser = subparsers.add_parser("list", help="list runs from the ledger")
    parser.add_argument("--limit", type=int, default=20)
    parser.set_defaults(handler=run)


def run(args: argparse.Namespace) -> int:
    entries = RunLedger().list_runs()[: args.limit]
    print_json([entry.model_dump() for entry in entries])
    return 0
