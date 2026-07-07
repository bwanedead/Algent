"""
Editorial-pipeline agent definition — profile -> finished article (planning + drafting).

Orchestrates the two gauntlets as sub-graphs. Rail-free: the orchestrator lives in
``pipeline.py``. Runs on a saved profile via ``--fixture``.
"""

from __future__ import annotations

from typing import Any

from algent_backend.agent_system.agents.agent_spec import AgentSpec, TestFixture
from algent_backend.agent_system.runs.context import AgentRunContext

from .pipeline import build_editorial_pipeline_graph

AGENT_ID = "editorial_pipeline"
RUNTIME = "langgraph"
FAMILY = "newsroom"


def build_graph(context: AgentRunContext) -> Any:
    return build_editorial_pipeline_graph(context)


SPEC = AgentSpec(
    agent_id=AGENT_ID,
    name="Editorial Pipeline",
    runtime=RUNTIME,
    build_graph=build_graph,
    description="Turns a research profile into a finished article (planning + drafting gauntlets).",
    default_model=None,     # orchestrator — sub-gauntlets carry their own models
    family=FAMILY,
    tool_ids=(),
    search_channels=None,
    test_fixture=TestFixture("fixtures/t2_profile_sample.json", "profile"),
)
