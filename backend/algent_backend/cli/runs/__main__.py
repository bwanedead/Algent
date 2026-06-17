"""
Dispatcher: ``python -m algent_backend.cli.runs <command> ...``

Commands: start, exec, status, watch, stop, list, show.
"""

from __future__ import annotations

import argparse
import sys

from . import exec_run, list_runs, show, start, status, stop, watch


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="python -m algent_backend.cli.runs",
        description="Algent run control plane (every command prints one JSON document).",
    )
    subparsers = parser.add_subparsers(dest="command", required=True)
    for module in (start, exec_run, status, watch, stop, list_runs, show):
        module.add_parser(subparsers)

    args = parser.parse_args(argv)
    return args.handler(args)


if __name__ == "__main__":
    sys.exit(main())
