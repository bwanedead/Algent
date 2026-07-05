"""
Drafting-gauntlet agent definition (v3a) — treatment+profile -> grounded ArticleDraft.

Orchestrates draft -> audit -> revise as a bounded, deterministic loop (the citation harness is
the gate; only the drafter sub-graph spends model tokens). Rail-free: the orchestrator lives in
``draft_gauntlet.py``. Runs on the combined {treatment, profile} fixture.
"""

from __future__ import annotations

from typing import Any

from algent_backend.agent_system.agents.agent_spec import AgentSpec, TestFixture
from algent_backend.agent_system.runs.context import AgentRunContext

from .draft_gauntlet import build_drafting_gauntlet_graph

AGENT_ID = "drafting_gauntlet"
RUNTIME = "langgraph"
FAMILY = "newsroom"


def build_graph(context: AgentRunContext) -> Any:
    return build_drafting_gauntlet_graph(context)


SPEC = AgentSpec(
    agent_id=AGENT_ID,
    name="Drafting Gauntlet",
    runtime=RUNTIME,
    build_graph=build_graph,
    description="Draft + audit + revise a piece until it clears the deterministic grounding floor.",
    default_model=None,     # orchestrator — the drafter sub-graph carries the model
    family=FAMILY,
    tool_ids=(),
    search_channels=None,
    test_fixture=TestFixture("fixtures/draft_input_sample.json", None),
)
