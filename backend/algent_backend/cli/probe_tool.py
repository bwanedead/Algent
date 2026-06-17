"""
Probe CLI — invoke any registered Algent tool live and inspect the results.

This is the manual evaluation surface for the sourcing portfolio: try a vendor,
eyeball the quality of what comes back, decide whether it earns a place in an
agent's workflow.

Usage:
    python -m algent_backend.cli.probe_tool <tool_id> <value>
    python -m algent_backend.cli.probe_tool <tool_id> key=value [key=value ...]
    python -m algent_backend.cli.probe_tool --list

A bare value is shorthand for ``query=<value>``. Examples:
    python -m algent_backend.cli.probe_tool web_search "ukraine ceasefire talks"
    python -m algent_backend.cli.probe_tool fetch_content url=https://example.com/article
    python -m algent_backend.cli.probe_tool rss_feed feed_url=https://feeds.bbci.co.uk/news/rss.xml
    python -m algent_backend.cli.probe_tool gdelt_events "taiwan strait" max_results=5
"""

from __future__ import annotations

import argparse
import json
import sys
from typing import Any

from ..agent_system.tools.registry import default_tool_registry


def _parse_params(raw: list[str]) -> dict[str, Any]:
    """Turn ['a=1', 'b=x'] (or a single bare value) into invoke kwargs."""
    params: dict[str, Any] = {}
    for item in raw:
        if "=" in item:
            key, _, value = item.partition("=")
            # Best-effort typing: ints pass through as ints, rest stay strings.
            params[key] = int(value) if value.isdigit() else value
        else:
            params["query"] = item
    return params


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Invoke a registered Algent tool live.")
    parser.add_argument("tool_id", nargs="?", help="Tool id (see --list).")
    parser.add_argument(
        "params",
        nargs="*",
        help="Bare value (becomes query=...) or key=value pairs.",
    )
    parser.add_argument("--list", action="store_true", help="List registered tools and exit.")
    args = parser.parse_args(argv)

    # Windows consoles default to cp1252 and crash on non-ASCII tool results;
    # force UTF-8, degrading un-encodable chars rather than raising.
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")

    registry = default_tool_registry()

    if args.list or not args.tool_id:
        for spec in sorted(registry.list(), key=lambda s: (s.channel, s.tool_id)):
            print(f"{spec.tool_id:18} [{spec.channel}/{spec.scope}] {spec.description}")
        return 0

    spec = registry.get(args.tool_id)
    # No params is valid — some tools take no arguments (e.g. a catalog lister),
    # and tools that do need args will report that themselves on invoke.
    params = _parse_params(args.params)

    print(f"probe: building '{spec.tool_id}' ({spec.channel}) ...", file=sys.stderr)
    tool = spec.build()
    print(f"probe: invoking with {params}", file=sys.stderr)
    result = tool.invoke(params)

    print(json.dumps(result, indent=2, ensure_ascii=False, default=str))
    return 0


if __name__ == "__main__":
    sys.exit(main())
