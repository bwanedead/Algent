"""
Primary-source enricher (gauntlet lane) — upgrades weak/aggregator sourcing to primary.

The first concrete enrichment lane: consumes a profile + its ReviewReport, acts on the
`primary_source` findings, deep-reads authoritative sources, and merges the new evidence in
(revision++). Rail-free spec; the machinery lives in ``base.py``.
"""

from __future__ import annotations

from typing import Any

from algent_backend.agent_system.agents.agent_spec import AgentSpec, TestFixture
from algent_backend.agent_system.foundation.models import openai_spec
from algent_backend.agent_system.runs.context import AgentRunContext
from algent_backend.agent_system.tools.sourcing.search import policy
from algent_backend.agent_system.tools.sourcing.search.research import WEB_SEARCH_TOOL_ID

from .base import build_enrich_graph
from .prompts import PRIMARY_SOURCE_PROMPT

AGENT_ID = "enrich_primary_source"
LANE = "primary_source"
TOOL_IDS = (WEB_SEARCH_TOOL_ID,)
SEARCH_CHANNELS = (policy.KEYWORD, policy.SEMANTIC, policy.READ, policy.RICH, policy.X)
PAID_BUDGET = 6
COST_CAP_USD = 1.00

DEFAULT_MODEL = openai_spec(reasoning_effort="medium", temperature=0.3, streaming=True)


def build_graph(context: AgentRunContext) -> Any:
    return build_enrich_graph(
        context, lane=LANE, model_spec=DEFAULT_MODEL, tool_ids=TOOL_IDS,
        system_prompt=PRIMARY_SOURCE_PROMPT, search_channels=SEARCH_CHANNELS,
        paid_budget=PAID_BUDGET, cost_cap_usd=COST_CAP_USD,
    )


SPEC = AgentSpec(
    agent_id=AGENT_ID,
    name="Primary-Source Enricher",
    runtime="langgraph",
    build_graph=build_graph,
    description="Gauntlet lane: upgrades a profile's weak/aggregator sourcing to deep-read primary sources.",
    default_model=DEFAULT_MODEL,
    family="newsroom",
    tool_ids=TOOL_IDS,
    search_channels=SEARCH_CHANNELS,
    # Isolated test: input is {profile, review} — fixture is the whole dict (no input_key).
    test_fixture=TestFixture("fixtures/enrich_input_sample.json", None),
)
