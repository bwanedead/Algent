"""
Signal-profile agent definition (t1 vector -> t2 profile).

Researches one selected signal vector into a signal profile (claim + source ledgers).
One tool — the unified ``web_search`` facade — used cheap-first. Free channels plus
paid ``rich`` (Firecrawl) for the occasional blocked page that matters; restraint is
structural (free-default tooling, doctrine, a hard paid budget, and a USD cap).
Rail-free: imports the loop builder, names no LangGraph types.
"""

from __future__ import annotations

from typing import Any

from algent_backend.agent_system.agents.agent_spec import AgentSpec, TestFixture
from algent_backend.agent_system.foundation.models import house_spec
from algent_backend.agent_system.runs.context import AgentRunContext
from algent_backend.agent_system.tools.sourcing.search import policy
from algent_backend.agent_system.tools.sourcing.search.research import WEB_SEARCH_TOOL_ID

from .loop import build_profile_graph
from .prompts import SYSTEM_PROMPT

AGENT_ID = "signal_profile"
RUNTIME = "langgraph"
FAMILY = "newsroom"
TOOL_IDS = (WEB_SEARCH_TOOL_ID,)
# Free channels + paid `rich` for hard/blocked pages + `x` for social/real-time signal.
SEARCH_CHANNELS = (policy.KEYWORD, policy.SEMANTIC, policy.READ, policy.RICH, policy.X)
PAID_BUDGET = 6          # hard ceiling on paid contacts per run
COST_CAP_USD = 1.00      # hard ceiling on estimated run spend; the loop auto-halts at it

DEFAULT_MODEL = house_spec(reasoning_effort="medium", temperature=0.3, streaming=True)


def build_graph(context: AgentRunContext) -> Any:
    return build_profile_graph(
        context,
        model_spec=DEFAULT_MODEL,
        tool_ids=TOOL_IDS,
        system_prompt=SYSTEM_PROMPT,
        search_channels=SEARCH_CHANNELS,
        paid_budget=PAID_BUDGET,
        cost_cap_usd=COST_CAP_USD,
    )


SPEC = AgentSpec(
    agent_id=AGENT_ID,
    name="Signal Profile",
    runtime=RUNTIME,
    build_graph=build_graph,
    description="Researches one signal vector into a t2 signal profile (claim + source ledgers).",
    default_model=DEFAULT_MODEL,
    family=FAMILY,
    tool_ids=TOOL_IDS,
    search_channels=SEARCH_CHANNELS,
    # Isolated test: research a saved selected vector (no router/synthesis) via `--fixture`.
    test_fixture=TestFixture("fixtures/t1_vector_sample.json", "vector"),
)
