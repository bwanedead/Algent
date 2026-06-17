"""
General discovery agent definition.

Goal-injectable: run it with no input for an open survey, or with
``{"goal": "..."}`` to target it (e.g. a research agent re-invoking discovery on
a topic of concern). Starts with two discovery channels — GDELT and RSS — and
adding more is a one-line change to ``TOOL_IDS``; the loop binds exactly what is
listed.

Rail-free, like every ``spec.py``: it imports the discovery loop builder but
names no LangGraph types. ``graph``/``loop`` never import this module.
"""

from __future__ import annotations

from typing import Any

from algent_backend.agent_system.agents.agent_spec import AgentSpec
from algent_backend.agent_system.foundation.models import ModelSpec
from algent_backend.agent_system.runs.context import AgentRunContext
from algent_backend.agent_system.tools.sourcing.discovery.gdelt import GDELT_EVENTS_TOOL_ID
from algent_backend.agent_system.tools.sourcing.discovery.news_feeds import NEWS_FEEDS_TOOL_ID
from algent_backend.agent_system.tools.sourcing.discovery.rss import RSS_FEED_TOOL_ID

from ..base import loop as discovery_loop
from .prompts import SYSTEM_PROMPT

AGENT_ID = "general_discovery"
RUNTIME = "langgraph"
FAMILY = "discovery"
# Discovery channels this agent binds: GDELT for what is being covered globally,
# news_feeds + rss_feed for reading real outlet feeds. Add a tool id to widen
# the sweep — no other change is needed.
TOOL_IDS = (GDELT_EVENTS_TOOL_ID, RSS_FEED_TOOL_ID, NEWS_FEEDS_TOOL_ID)
# Initial brain: a cheap, fast model (swap freely via ModelSpec — discovery is
# judgment-heavy, so this is the dial most likely worth tuning). `extra` carries
# OpenAI-specific knobs: streaming for diagnostics, stream_usage so token totals
# still roll up while streaming.
DEFAULT_MODEL = ModelSpec(
    provider="openai",
    model="gpt-5.4-mini",
    temperature=0.4,
    extra={"streaming": True, "stream_usage": True},
)


def build_graph(context: AgentRunContext) -> Any:
    """Build the discovery graph with this agent's model, tools, and prompt."""
    return discovery_loop.build_discovery_graph(
        context,
        model_spec=DEFAULT_MODEL,
        tool_ids=TOOL_IDS,
        system_prompt=SYSTEM_PROMPT,
    )


SPEC = AgentSpec(
    agent_id=AGENT_ID,
    name="General Discovery",
    runtime=RUNTIME,
    build_graph=build_graph,
    description="Surveys discovery channels (GDELT, RSS) for notable topics worth deeper work.",
    default_model=DEFAULT_MODEL,
    family=FAMILY,
    tool_ids=TOOL_IDS,
)
