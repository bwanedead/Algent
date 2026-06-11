"""
ToolSpec — Algent tool metadata plus an in-process builder.

A tool is a *capability* an agent can use (search the web, query a graph, call an
API), not an output. ``ToolSpec`` carries neutral metadata and a ``build``
callable that constructs the concrete tool object. The first concrete tool builds
a LangChain tool — but that detail lives in the tool module, never here. This
module imports neither LangChain nor LangGraph.

Scope is a simple string convention, not a permissions engine:

    "global"            available to every agent
    "family:<family>"   available to agents in a family (e.g. "family:news")
    "agent:<agent_id>"  available to one agent

``ToolRegistry.resolve_for`` matches an agent against these.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

GLOBAL_SCOPE = "global"


def family_scope(family: str) -> str:
    return f"family:{family}"


def agent_scope(agent_id: str) -> str:
    return f"agent:{agent_id}"


@dataclass(frozen=True)
class ToolSpec:
    """Metadata and builder for one tool capability."""

    tool_id: str
    name: str
    description: str
    scope: str
    build: Callable[[], Any]
    # Capability channel for portfolio grouping — lets orchestration ask for
    # e.g. all "search" tools and fan out. Conventional values:
    # "search" | "social" | "depth" | "discovery" | "general".
    channel: str = "general"
