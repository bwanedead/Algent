"""
Discovery synthesis agent definition (t0 -> t1).

Consumes the deterministic discovery pool (t0) and produces the research-vector
portfolio (t1). One tool — the unified ``web_search`` facade — used cheap-first.
All search channels are granted (the agent may escalate to paid when needed), but
restraint is enforced by free-by-default tooling, doctrine, and a hard per-run
paid-call budget. Rail-free: imports the loop builder, names no LangGraph types.
"""

from __future__ import annotations

from typing import Any

from algent_backend.agent_system.agents.agent_spec import AgentSpec, TestFixture
from algent_backend.agent_system.foundation.models import house_spec
from algent_backend.agent_system.runs.context import AgentRunContext
from algent_backend.agent_system.tools.sourcing.search import policy
from algent_backend.agent_system.tools.sourcing.search.research import WEB_SEARCH_TOOL_ID

from .loop import build_synthesis_graph
from .prompts import SYSTEM_PROMPT

AGENT_ID = "discovery_synthesis"
RUNTIME = "langgraph"
FAMILY = "discovery"
TOOL_IDS = (WEB_SEARCH_TOOL_ID,)
# Granted all channels (free + paid) so the agent can escalate when free is dry.
# Restraint is structural: free-default tooling + doctrine + the paid budget below.
SEARCH_CHANNELS = (policy.KEYWORD, policy.SEMANTIC, policy.READ, policy.RICH, policy.X)
# Hard ceiling on paid contacts per run — the runaway-cost backstop.
PAID_BUDGET = 8
# Hard ceiling on *estimated* total run spend (model tokens + paid calls). The
# loop auto-halts when the estimate crosses this. Conservative for live testing.
COST_CAP_USD = 1.00

DEFAULT_MODEL = house_spec(reasoning_effort="medium", temperature=0.3, streaming=True)


def build_graph(context: AgentRunContext) -> Any:
    return build_synthesis_graph(
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
    name="Discovery Synthesis",
    runtime=RUNTIME,
    build_graph=build_graph,
    description="Turns the t0 discovery pool into a t1 research-vector portfolio.",
    default_model=DEFAULT_MODEL,
    family=FAMILY,
    tool_ids=TOOL_IDS,
    search_channels=SEARCH_CHANNELS,
    # Isolated test: run synthesis on a saved t0 pool (no GDELT) via `--fixture`.
    test_fixture=TestFixture("fixtures/t0_pool_sample.json", "pool"),
)
