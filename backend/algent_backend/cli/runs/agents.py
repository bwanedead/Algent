"""
``agents`` — list the agents you can start.

The runnable catalog (``AgentRegistry``) as JSON: each agent's id, what it is,
its runtime, family, tools, and default model. This is how an operator or a
testing agent discovers what ``start <agent_id>`` will accept.
"""

from __future__ import annotations

import argparse

from algent_backend.agent_system.agents.registry import default_agent_registry

from ._shared import print_json


def add_parser(subparsers: argparse._SubParsersAction) -> None:
    parser = subparsers.add_parser("agents", help="list the agents available to start")
    parser.set_defaults(handler=run)


def run(args: argparse.Namespace) -> int:
    registry = default_agent_registry()
    catalog = []
    for spec in sorted(registry.list(), key=lambda s: s.agent_id):
        model = None
        if spec.default_model is not None:
            model = {"provider": spec.default_model.provider, "model": spec.default_model.model}
        catalog.append(
            {
                "agent_id": spec.agent_id,
                "name": spec.name,
                "description": spec.description,
                "runtime": spec.runtime,
                "family": spec.family,
                "tools": list(spec.tool_ids),
                "model": model,
            }
        )
    print_json(catalog)
    return 0
