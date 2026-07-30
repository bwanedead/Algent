"""
Article-drafter agent definition — promoted treatment -> ArticleDraft (+ enriched profile).

The most autonomous editorial stage: it researches for precision (one tool — the unified
``web_search`` facade, cheap-first, same restraint structure as the profile researcher),
writes the prose, and feeds findings back into the profile. Rail-free: imports the loop
builder, names no LangGraph types.
"""

from __future__ import annotations

from typing import Any

from algent_backend.agent_system.agents.agent_spec import AgentSpec, TestFixture
from algent_backend.agent_system.foundation.models import openai_spec
from algent_backend.agent_system.runs.context import AgentRunContext
from algent_backend.agent_system.tools.sourcing.search import policy
from algent_backend.agent_system.tools.sourcing.search.research import WEB_SEARCH_TOOL_ID

from .draft_loop import build_draft_graph
from .draft_prompts import SYSTEM_PROMPT

AGENT_ID = "article_drafter"
RUNTIME = "langgraph"
FAMILY = "newsroom"
TOOL_IDS = (WEB_SEARCH_TOOL_ID,)
# Free channels + paid `rich` for the occasional blocked primary that sharpens the piece.
SEARCH_CHANNELS = (policy.KEYWORD, policy.SEMANTIC, policy.READ, policy.RICH, policy.X)
PAID_BUDGET = 4          # lighter than research — drafting is precision, not discovery
COST_CAP_USD = 1.00

DEFAULT_MODEL = openai_spec(reasoning_effort="medium", temperature=0.4, streaming=True)


def build_graph(context: AgentRunContext) -> Any:
    return build_draft_graph(
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
    name="Article Drafter",
    runtime=RUNTIME,
    build_graph=build_graph,
    description="Writes a promoted treatment into prose, researching for precision + enriching the profile.",
    default_model=DEFAULT_MODEL,
    family=FAMILY,
    tool_ids=TOOL_IDS,
    search_channels=SEARCH_CHANNELS,
    # Needs both a treatment and its profile: the fixture is the whole state (input_key=None).
    test_fixture=TestFixture("fixtures/draft_input_sample.json", None),
)
