"""``sources`` — list the registered ingestion sources and what each supports."""

from __future__ import annotations

import argparse

from ._shared import DIGESTABLE, SOURCES, print_json


def add_parser(subparsers: argparse._SubParsersAction) -> None:
    parser = subparsers.add_parser("sources", help="list registered ingestion sources")
    parser.set_defaults(handler=run)


def run(args: argparse.Namespace) -> int:
    print_json(
        [
            {
                "source": source_id,
                "module": module.__name__,
                "can_fetch": hasattr(module, "fetch_latest_raw"),
                "can_digest": source_id in DIGESTABLE,
            }
            for source_id, module in sorted(SOURCES.items())
        ]
    )
    return 0
