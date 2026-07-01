"""
Signal-router agent definition (t1 -> t2 promotion).

Ranks the t1 signal portfolio and selects the top vector to promote into a profile.
Pure judgment — no tools, no search channels; one structured model call. Rail-free:
names no LangGraph types (the graph builder lives in ``run_graph.py``).
"""

from __future__ import annotations

from typing import Any

from algent_backend.agent_system.agents.agent_spec import AgentSpec, TestFixture
from algent_backend.agent_system.foundation.models import ModelSpec
from algent_backend.agent_system.runs.context import AgentRunContext

from .run_graph import build_signal_router_graph

AGENT_ID = "signal_router"
RUNTIME = "langgraph"
FAMILY = "newsroom"

# Coarse ranking/selection over supplied candidates — the nano tier is plenty here (it
# reasons over given text into a structured pick, no research, no generation).
DEFAULT_MODEL = ModelSpec(provider="openai", model="gpt-5.4-nano", temperature=0.2)


def build_graph(context: AgentRunContext) -> Any:
    return build_signal_router_graph(context, model_spec=DEFAULT_MODEL)


SPEC = AgentSpec(
    agent_id=AGENT_ID,
    name="Signal Router",
    runtime=RUNTIME,
    build_graph=build_graph,
    description="Ranks the t1 signal portfolio and selects the top vector to promote into a profile.",
    default_model=DEFAULT_MODEL,
    family=FAMILY,
    tool_ids=(),            # no tools — pure ranking judgment
    search_channels=None,
    # Isolated test: rank a saved t1 portfolio (no synthesis) via `--fixture`.
    test_fixture=TestFixture("fixtures/t1_portfolio_sample.json", "portfolio"),
)
