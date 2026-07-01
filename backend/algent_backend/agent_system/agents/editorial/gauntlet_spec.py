"""
Planning-gauntlet agent definition — profile -> promoted EditorialTreatment.

Orchestrates plan -> review -> (revise -> re-review) as one bounded round, invoking the
editorial_planner and treatment_reviewer as sub-graphs. Rail-free: the orchestrator lives in
``gauntlet.py``. Runs on the profile fixture via ``--fixture``.
"""

from __future__ import annotations

from typing import Any

from algent_backend.agent_system.agents.agent_spec import AgentSpec, TestFixture
from algent_backend.agent_system.runs.context import AgentRunContext

from .gauntlet import build_planning_gauntlet_graph

AGENT_ID = "planning_gauntlet"
RUNTIME = "langgraph"
FAMILY = "newsroom"


def build_graph(context: AgentRunContext) -> Any:
    return build_planning_gauntlet_graph(context)


SPEC = AgentSpec(
    agent_id=AGENT_ID,
    name="Planning Gauntlet",
    runtime=RUNTIME,
    build_graph=build_graph,
    description="Plan + review + revise a treatment until promotion (one bounded round).",
    default_model=None,     # orchestrator — sub-agents carry their own models
    family=FAMILY,
    tool_ids=(),
    search_channels=None,
    test_fixture=TestFixture("fixtures/t2_profile_sample.json", "profile"),
)
