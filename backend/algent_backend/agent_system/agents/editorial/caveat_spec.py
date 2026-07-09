"""
Caveat-reviewer agent definition — v3b's semantic honesty lane.

Verifies a finished draft keeps the specific promises the harness flagged (grade-appropriate
wording, hedged un-read sources, dated volatile figures). Tool-free; nano tier (a focused check
over a small supplied list, not a free-roaming review); short-circuits to free when nothing is
flagged. Rail-free: the graph builder lives in ``caveat_loop.py``.
"""

from __future__ import annotations

from typing import Any

from algent_backend.agent_system.agents.agent_spec import AgentSpec
from algent_backend.agent_system.foundation.models import ModelSpec
from algent_backend.agent_system.runs.context import AgentRunContext

from .caveat_loop import build_caveat_reviewer_graph

AGENT_ID = "caveat_reviewer"
RUNTIME = "langgraph"
FAMILY = "newsroom"

# A narrow check over a small pre-computed list — the nano tier is plenty (and the point).
DEFAULT_MODEL = ModelSpec(provider="openai", model="gpt-5.4-nano", temperature=0.2)


def build_graph(context: AgentRunContext) -> Any:
    return build_caveat_reviewer_graph(context, model_spec=DEFAULT_MODEL)


SPEC = AgentSpec(
    agent_id=AGENT_ID,
    name="Caveat Reviewer",
    runtime=RUNTIME,
    build_graph=build_graph,
    description="Verifies a draft's prose keeps its flagged promises (hedging/grade/as-of). v3b.",
    default_model=DEFAULT_MODEL,
    family=FAMILY,
    tool_ids=(),
    search_channels=None,
    test_fixture=None,   # needs draft + profile; exercised via the pipeline / unit tests
)
