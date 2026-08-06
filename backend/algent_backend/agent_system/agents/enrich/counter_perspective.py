"""
Counter-perspective enricher (gauntlet lane) — adversarial completeness.

The second enrichment lane: consumes a profile + its ReviewReport, acts on the
`counter_perspective` findings (one-sidedness, missing perspectives, overclaiming,
too-clean framing), finds the strongest opposing case and dissent, and merges the new
evidence in (revision++). Same engine as the primary_source lane — only the doctrine
differs. Rail-free spec.
"""

from __future__ import annotations

from typing import Any

from algent_backend.agent_system.agents.agent_spec import AgentSpec, TestFixture
from algent_backend.agent_system.foundation.models import house_spec
from algent_backend.agent_system.runs.context import AgentRunContext
from algent_backend.agent_system.tools.sourcing.search import policy
from algent_backend.agent_system.tools.sourcing.search.research import WEB_SEARCH_TOOL_ID

from .base import build_enrich_graph
from .prompts import COUNTER_PERSPECTIVE_PROMPT

AGENT_ID = "enrich_counter_perspective"
LANE = "counter_perspective"
TOOL_IDS = (WEB_SEARCH_TOOL_ID,)
SEARCH_CHANNELS = (policy.KEYWORD, policy.SEMANTIC, policy.READ, policy.RICH, policy.X)
PAID_BUDGET = 6
COST_CAP_USD = 1.00

DEFAULT_MODEL = house_spec(reasoning_effort="medium", temperature=0.3, streaming=True)


def build_graph(context: AgentRunContext) -> Any:
    return build_enrich_graph(
        context, lane=LANE, model_spec=DEFAULT_MODEL, tool_ids=TOOL_IDS,
        system_prompt=COUNTER_PERSPECTIVE_PROMPT, search_channels=SEARCH_CHANNELS,
        paid_budget=PAID_BUDGET, cost_cap_usd=COST_CAP_USD,
    )


SPEC = AgentSpec(
    agent_id=AGENT_ID,
    name="Counter-Perspective Enricher",
    runtime="langgraph",
    build_graph=build_graph,
    description="Gauntlet lane: rounds out a one-sided profile with the strongest opposing case and dissent.",
    default_model=DEFAULT_MODEL,
    family="newsroom",
    tool_ids=TOOL_IDS,
    search_channels=SEARCH_CHANNELS,
    test_fixture=TestFixture("fixtures/enrich_input_sample.json", None),
)
