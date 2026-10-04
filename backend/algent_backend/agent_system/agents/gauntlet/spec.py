"""
Gauntlet orchestrator agent — runs one bounded review/enrichment round over a profile.

Declares web_search in its tools so the enricher sub-graphs (which it invokes) can reach
the facade; each enricher scopes its own policy/budget internally. Rail-free spec.
"""

from __future__ import annotations

from typing import Any

from algent_backend.agent_system.agents.agent_spec import AgentSpec, TestFixture
from algent_backend.agent_system.foundation.models import house_spec
from algent_backend.agent_system.runs.context import AgentRunContext
from algent_backend.agent_system.tools.sourcing.search import policy
from algent_backend.agent_system.tools.sourcing.search.research import WEB_SEARCH_TOOL_ID

from .orchestrator import build_gauntlet_graph

AGENT_ID = "profile_gauntlet"
RUNTIME = "langgraph"
FAMILY = "newsroom"
# Tools must be resolvable so the enricher sub-graphs can use web_search (they self-gate).
TOOL_IDS = (WEB_SEARCH_TOOL_ID,)
SEARCH_CHANNELS = (policy.KEYWORD, policy.SEMANTIC, policy.READ, policy.RICH)

# The orchestrator itself does no model work; sub-graphs carry their own models.
DEFAULT_MODEL = house_spec(reasoning_effort="medium")


def build_graph(context: AgentRunContext) -> Any:
    return build_gauntlet_graph(context)


SPEC = AgentSpec(
    agent_id=AGENT_ID,
    name="Profile Gauntlet",
    runtime=RUNTIME,
    build_graph=build_graph,
    description="Runs one bounded review -> enrich -> merge -> re-review round over a profile.",
    default_model=DEFAULT_MODEL,
    family=FAMILY,
    tool_ids=TOOL_IDS,
    search_channels=SEARCH_CHANNELS,
    # Isolated test: put a saved profile through the gauntlet via `--fixture`.
    test_fixture=TestFixture("fixtures/t2_profile_sample.json", "profile"),
)
