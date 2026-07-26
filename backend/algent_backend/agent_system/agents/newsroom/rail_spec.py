"""
Full newsroom-rail agent definition — raw discovery pool -> finished article, one run.

Orchestrates the five proven stages as sub-graphs under one run (discovery synthesis -> routing ->
profile -> profile gauntlet -> editorial pipeline). Rail-free: the orchestrator lives in ``rail.py``;
each stage carries its own model, budgets, and floors. Run the whole rail from nothing with:

    runs start newsroom_rail            # self-sources t0 + reads the backfeed queue

Or reuse a prior run's t1 portfolio (skip t0+synthesis cost; same promotion cooldown
as a fresh run — cooled story-families stay blocked) with:

    runs start newsroom_rail --from-run <run_id|NNNN|path>
"""

from __future__ import annotations

from typing import Any

from algent_backend.agent_system.agents.agent_spec import AgentSpec
from algent_backend.agent_system.runs.context import AgentRunContext

from .rail import build_newsroom_rail_graph

AGENT_ID = "newsroom_rail"
RUNTIME = "langgraph"
FAMILY = "newsroom"


def build_graph(context: AgentRunContext) -> Any:
    return build_newsroom_rail_graph(context)


SPEC = AgentSpec(
    agent_id=AGENT_ID,
    name="Newsroom Rail",
    runtime=RUNTIME,
    build_graph=build_graph,
    description="Raw discovery pool -> finished article: synthesis, routing, profile, gauntlet, editorial.",
    default_model=None,     # orchestrator — every sub-stage carries its own model + floors
    family=FAMILY,
    tool_ids=(),
    search_channels=None,
    # No fixture: the rail self-sources its own t0 pool (and reads the backfeed queue), so a bare
    # `runs start newsroom_rail` is the whole input.
    test_fixture=None,
)
