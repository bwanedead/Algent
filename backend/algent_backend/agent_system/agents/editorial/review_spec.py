"""
Treatment-reviewer agent definition — the planning gauntlet's critique stage.

Reviews an EditorialTreatment against its source profile and emits a task-generating
TreatmentReview. Tool-free (pure judgment; fresh eyes the planner cannot turn on itself).
Rail-free: the graph builder lives in ``review_loop.py``.
"""

from __future__ import annotations

from typing import Any

from algent_backend.agent_system.agents.agent_spec import AgentSpec
from algent_backend.agent_system.foundation.models import openai_spec
from algent_backend.agent_system.runs.context import AgentRunContext

from .review_loop import build_treatment_reviewer_graph

AGENT_ID = "treatment_reviewer"
RUNTIME = "langgraph"
FAMILY = "newsroom"

# Structured critique over a supplied treatment + profile, backed by a re-review — the nano
# tier is enough (judges given text into findings; does not research or generate prose).
DEFAULT_MODEL = openai_spec(reasoning_effort="low", temperature=0.2)


def build_graph(context: AgentRunContext) -> Any:
    return build_treatment_reviewer_graph(context, model_spec=DEFAULT_MODEL)


SPEC = AgentSpec(
    agent_id=AGENT_ID,
    name="Treatment Reviewer",
    runtime=RUNTIME,
    build_graph=build_graph,
    description="Reviews an EditorialTreatment against its profile (planning gauntlet critique stage).",
    default_model=DEFAULT_MODEL,
    family=FAMILY,
    tool_ids=(),            # no tools — judges the existing treatment
    search_channels=None,
    # Needs both a treatment and its profile; exercised via the planning gauntlet, not a
    # single-file fixture (no test_fixture — the gauntlet supplies both inputs).
    test_fixture=None,
)
