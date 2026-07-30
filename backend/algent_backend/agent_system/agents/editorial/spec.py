"""
Editorial-planner agent definition — the article pipeline's planning stage.

Reads a researched profile and produces an EditorialTreatment (the frame + the
concept-molecule the drafter will inherit). Tool-free (pure judgment over the profile; the
research already did the searching). Rail-free: the graph builder lives in ``loop.py``.
"""

from __future__ import annotations

from typing import Any

from algent_backend.agent_system.agents.agent_spec import AgentSpec, TestFixture
from algent_backend.agent_system.foundation.models import openai_spec
from algent_backend.agent_system.runs.context import AgentRunContext

from .loop import build_planning_graph

AGENT_ID = "editorial_planner"
RUNTIME = "langgraph"
FAMILY = "newsroom"

# Framing + molecule design over one profile — the savvy tier, one structured call. A touch
# of temperature: choosing a frame means generating genuinely different candidate vantages.
DEFAULT_MODEL = openai_spec(reasoning_effort="medium", temperature=0.35)


def build_graph(context: AgentRunContext) -> Any:
    return build_planning_graph(context, model_spec=DEFAULT_MODEL)


SPEC = AgentSpec(
    agent_id=AGENT_ID,
    name="Editorial Planner",
    runtime=RUNTIME,
    build_graph=build_graph,
    description="Plans an article: profile -> EditorialTreatment (frame + concept-molecule).",
    default_model=DEFAULT_MODEL,
    family=FAMILY,
    tool_ids=(),            # no tools — judges the existing profile
    search_channels=None,
    # Isolated test: plan from a saved profile via `--fixture`.
    test_fixture=TestFixture("fixtures/t2_profile_sample.json", "profile"),
)
