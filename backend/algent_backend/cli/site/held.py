"""``site held`` — the held-queue ledger: pieces the floors kept off the site, and why."""

from __future__ import annotations

import argparse

from algent_backend.publishing import site_git

from ..runs._shared import print_json


def add_parser(subparsers: argparse._SubParsersAction) -> None:
    parser = subparsers.add_parser("held", help="show the held-queue ledger (pieces not published, with reasons)")
    parser.set_defaults(handler=run)


def run(args: argparse.Namespace) -> int:
    root = site_git.repo_root()
    ledger = root / "backend" / "publish_held" / "held-ledger.md"
    published = root.joinpath("sites", "ohmega-monster", "publish-ledger.md")
    print_json({
        "held_ledger": ledger.read_text(encoding="utf-8") if ledger.exists() else "(nothing held)",
        "publish_ledger_exists": published.exists(),
        "held_ledger_path": str(ledger),
    })
    return 0
