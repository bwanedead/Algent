"""
Dispatcher: ``python -m algent_backend.data_ingestion.cli <command> ...``

Commands: ingest.
"""

from __future__ import annotations

import argparse
import sys

from . import ingest


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="python -m algent_backend.data_ingestion.cli",
        description="Algent data-ingestion pipeline (every command prints one JSON document).",
    )
    subparsers = parser.add_subparsers(dest="command", required=True)
    for module in (ingest,):
        module.add_parser(subparsers)

    args = parser.parse_args(argv)
    return args.handler(args)


if __name__ == "__main__":
    sys.exit(main())
