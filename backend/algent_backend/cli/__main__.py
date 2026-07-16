"""
Unified Algent control surface: ``python -m algent_backend.cli <category> <command>``.

One entry point, two categories today — both print exactly one JSON document, so
humans, scripts, and agents drive everything the same way:

- ``runs``   — the agent run control plane (start/watch/stop/... a discovery run).
- ``ingest`` — data-ingestion pipelines (fetch/unpack a source, digest it, ...).

This is the integration point the rest of the system targets; the per-category
dispatchers (``algent_backend.cli.runs``, ``algent_backend.data_ingestion.cli``)
remain valid entry points and register the very same command modules.

    python -m algent_backend.cli runs start general_discovery
    python -m algent_backend.cli ingest fetch gdelt_ngrams
"""

from __future__ import annotations

import argparse
import sys

from algent_backend.data_ingestion.cli import COMMANDS as INGEST_COMMANDS

from .runs import agents, exec_run, list_runs, show, start, status, stop, watch
from .site import held as site_held
from .site import publish as site_publish
from .site import retract as site_retract

RUNS_COMMANDS = (start, exec_run, status, watch, stop, agents, list_runs, show)
SITE_COMMANDS = (site_publish, site_retract, site_held)

# Category id -> (help, command modules registered under it).
_CATEGORIES = {
    "runs": ("agent run control plane", RUNS_COMMANDS),
    "ingest": ("data-ingestion pipelines", INGEST_COMMANDS),
    "site": ("publish finished runs to the live site", SITE_COMMANDS),
}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="python -m algent_backend.cli",
        description="Algent control surface (every command prints one JSON document).",
    )
    categories = parser.add_subparsers(dest="category", required=True)
    for name, (help_text, modules) in _CATEGORIES.items():
        category_parser = categories.add_parser(name, help=help_text)
        commands = category_parser.add_subparsers(dest="command", required=True)
        for module in modules:
            module.add_parser(commands)

    args = parser.parse_args(argv)
    return args.handler(args)


if __name__ == "__main__":
    sys.exit(main())
