"""
Headline-writer agent definition — a post-draft pass that titles the finished piece.

Tool-free; nano tier (a short focused write over the finished prose). Rail-free: the graph
builder lives in ``headline_loop.py``.
"""

from __future__ import annotations

from typing import Any

from algent_backend.agent_system.agents.agent_spec import AgentSpec
from algent_backend.agent_system.foundation.models import ModelSpec
from algent_backend.agent_system.runs.context import AgentRunContext

from .headline_loop import build_headline_writer_graph

AGENT_ID = "headline_writer"
RUNTIME = "langgraph"
FAMILY = "newsroom"

DEFAULT_MODEL = ModelSpec(provider="openai", model="gpt-5.4-nano", temperature=0.4)


def build_graph(context: AgentRunContext) -> Any:
    return build_headline_writer_graph(context, model_spec=DEFAULT_MODEL)


SPEC = AgentSpec(
    agent_id=AGENT_ID,
    name="Headline Writer",
    runtime=RUNTIME,
    build_graph=build_graph,
    description="Writes a truthful headline + dek for a finished article (headline-guidance.md).",
    default_model=DEFAULT_MODEL,
    family=FAMILY,
    tool_ids=(),
    search_channels=None,
    test_fixture=None,
)
