"""
Profile-reviewer agent definition — the gauntlet's first stage.

Reviews a research profile and emits a task-generating ReviewReport. Tool-free (pure
judgment over the existing profile; the enrichers do the searching). Rail-free: names no
LangGraph types (the graph builder lives in ``loop.py``).
"""

from __future__ import annotations

from typing import Any

from algent_backend.agent_system.agents.agent_spec import AgentSpec, TestFixture
from algent_backend.agent_system.foundation.models import ModelSpec
from algent_backend.agent_system.runs.context import AgentRunContext

from .loop import build_reviewer_graph

AGENT_ID = "profile_reviewer"
RUNTIME = "langgraph"
FAMILY = "newsroom"

# Editorial judgment over one profile — the savvy tier, one structured call.
DEFAULT_MODEL = ModelSpec(provider="openai", model="gpt-5.4-mini", temperature=0.2)


def build_graph(context: AgentRunContext) -> Any:
    return build_reviewer_graph(context, model_spec=DEFAULT_MODEL)


SPEC = AgentSpec(
    agent_id=AGENT_ID,
    name="Profile Reviewer",
    runtime=RUNTIME,
    build_graph=build_graph,
    description="Reviews a research profile and emits a task-generating critique (gauntlet stage 1).",
    default_model=DEFAULT_MODEL,
    family=FAMILY,
    tool_ids=(),            # no tools — judges the existing profile
    search_channels=None,
    # Isolated test: review a saved profile via `--fixture`.
    test_fixture=TestFixture("fixtures/t2_profile_sample.json", "profile"),
)
