"""
Discovery synthesis agent definition (t0 -> t1).

Consumes the deterministic discovery pool (t0) and produces the research-vector
portfolio (t1) — the menu. No tools: it judges from the pool lines, in one structured reply.
It used to web-search while writing the menu (~10 paid calls) and think at medium effort
across every turn, re-sending the whole pool each time — 9 to 20+ minutes for what is a
list of forty-odd titles with a line each. The picked vector is researched properly by the
profile stage; the menu does not need to pre-research every candidate.
Rail-free: imports the loop builder, names no LangGraph types.
"""

from __future__ import annotations

from typing import Any

from algent_backend.agent_system.agents.agent_spec import AgentSpec, TestFixture
from algent_backend.agent_system.foundation.models import house_spec
from algent_backend.agent_system.runs.context import AgentRunContext

from .loop import build_synthesis_graph
from .prompts import SYSTEM_PROMPT

AGENT_ID = "discovery_synthesis"
RUNTIME = "langgraph"
FAMILY = "discovery"
TOOL_IDS: tuple[str, ...] = ()
SEARCH_CHANNELS: tuple[str, ...] = ()
PAID_BUDGET = 0
# Hard ceiling on *estimated* total run spend (model tokens + paid calls). The
# loop auto-halts when the estimate crosses this. Conservative for live testing.
COST_CAP_USD = 1.00

# Low effort: sorting and naming leads, not analysing them.
DEFAULT_MODEL = house_spec(reasoning_effort="low", temperature=0.3, streaming=True)


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
