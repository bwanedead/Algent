"""
News brief agent definition.

The first real agent: it performs live web search through the tool seam and
writes a grounded brief. Owns identity, family, tool needs, default model, and
the ``SPEC`` recipe the ``AgentRegistry`` registers. Imports ``graph``; ``graph``
never imports this module.
"""

from __future__ import annotations

from typing import Any

from algent_backend.agent_system.agents.agent_spec import AgentSpec
from algent_backend.agent_system.foundation.models import ModelSpec
from algent_backend.agent_system.runs.context import AgentRunContext
from algent_backend.agent_system.tools.shared.web_search import WEB_SEARCH_TOOL_ID

from . import graph

AGENT_ID = "news_brief"
RUNTIME = "langgraph"
FAMILY = "news"
DEFAULT_MODEL = ModelSpec(provider="anthropic", model="claude-sonnet-4-5", temperature=0.3)


def build_graph(context: AgentRunContext) -> Any:
    """Build the news brief graph with this agent's default model."""
    return graph.build_graph(context, DEFAULT_MODEL)


SPEC = AgentSpec(
    agent_id=AGENT_ID,
    name="News Brief",
    runtime=RUNTIME,
    build_graph=build_graph,
    description="Researches a topic via web search and writes a grounded news brief.",
    default_model=DEFAULT_MODEL,
    family=FAMILY,
    tool_ids=(WEB_SEARCH_TOOL_ID,),
)
