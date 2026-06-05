"""
Hello workflow agent definition.

Owns agent identity, runtime choice, default model, and the ``SPEC`` recipe that
the ``AgentRegistry`` registers. This module imports ``graph``; ``graph`` never
imports this module, which keeps the import direction acyclic.
"""

from __future__ import annotations

from typing import Any

from algent_backend.agent_system.agents.agent_spec import AgentSpec
from algent_backend.agent_system.foundation.models import ModelSpec
from algent_backend.agent_system.runs.context import AgentRunContext

from . import graph

AGENT_ID = "hello_workflow"
RUNTIME = "langgraph"
DEFAULT_MODEL = ModelSpec(provider="anthropic", model="claude-sonnet-4-5", temperature=0.2)


def build_graph(context: AgentRunContext) -> Any:
    """Build the hello workflow graph with this agent's default model."""
    return graph.build_graph(context, DEFAULT_MODEL)


SPEC = AgentSpec(
    agent_id=AGENT_ID,
    name="Hello Workflow",
    runtime=RUNTIME,
    build_graph=build_graph,
    description="Generates a one-sentence brief about a topic.",
    default_model=DEFAULT_MODEL,
)
