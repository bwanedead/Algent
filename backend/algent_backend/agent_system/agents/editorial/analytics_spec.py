"""
Analytics-router agent definition — assesses a profile for analytics opportunities.

Tool-free; nano tier (a focused judgment over the profile). The (sandboxed) grok-build worker that
fulfills the requests is a separate, later stage. Rail-free: the graph builder lives in
``analytics_router.py``.
"""

from __future__ import annotations

from typing import Any

from algent_backend.agent_system.agents.agent_spec import AgentSpec, TestFixture
from algent_backend.agent_system.foundation.models import ModelSpec
from algent_backend.agent_system.runs.context import AgentRunContext

from .analytics_router import build_analytics_router_graph

AGENT_ID = "analytics_router"
RUNTIME = "langgraph"
FAMILY = "newsroom"

DEFAULT_MODEL = ModelSpec(provider="openai", model="gpt-5.4-nano", temperature=0.2)


def build_graph(context: AgentRunContext) -> Any:
    return build_analytics_router_graph(context, model_spec=DEFAULT_MODEL)


SPEC = AgentSpec(
    agent_id=AGENT_ID,
    name="Analytics Router",
    runtime=RUNTIME,
    build_graph=build_graph,
    description="Assesses a profile for analytics opportunities and emits grounded requests.",
    default_model=DEFAULT_MODEL,
    family=FAMILY,
    tool_ids=(),
    search_channels=None,
    test_fixture=TestFixture("fixtures/t2_profile_sample.json", "profile"),
)
