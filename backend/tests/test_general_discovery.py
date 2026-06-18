"""
Offline tests for the general discovery agent and discovery scaffolding.

These cover the pieces that are stable without a live model: output contracts and
the cap backstop, the task-message shaping, prompt composition, agent
registration, and tool resolution. The live ReAct loop (create_react_agent over a
real model with keys) is validated by running the agent, not here.
"""

from __future__ import annotations

from types import SimpleNamespace

from algent_backend.agent_system.agents.discovery.base.contracts import (
    DiscoveryResult,
    TopicCandidate,
    cap_candidates,
)
from algent_backend.agent_system.agents.discovery.base.messages import build_task_message
from algent_backend.agent_system.agents.discovery.general import spec as general_spec
from algent_backend.agent_system.agents.discovery.general.prompts import SYSTEM_PROMPT
from algent_backend.agent_system.agents.loop import stream_react_loop
from algent_backend.agent_system.agents.registry import default_agent_registry
from algent_backend.agent_system.tools import default_tool_registry
from algent_backend.agent_system.tools.sourcing.discovery.gdelt import GDELT_EVENTS_TOOL_ID
from algent_backend.agent_system.tools.sourcing.discovery.news_feeds import NEWS_FEEDS_TOOL_ID
from algent_backend.agent_system.tools.sourcing.discovery.rss import RSS_FEED_TOOL_ID


def _candidates(n: int) -> list[TopicCandidate]:
    return [TopicCandidate(title=f"t{i}", why_notable="because") for i in range(n)]


class _CapturingContext:
    def __init__(self) -> None:
        self.events: list[tuple[str, dict]] = []

    def emit(self, event_type: str, payload: dict | None = None) -> None:
        self.events.append((event_type, payload or {}))


class _FakeStreamAgent:
    """Stands in for a compiled ReAct agent: yields the given update chunks."""

    def __init__(self, chunks: list[dict]) -> None:
        self._chunks = chunks

    def stream(self, inputs, config=None, stream_mode=None):
        yield from self._chunks


def test_stream_react_loop_emits_turn_events_and_returns_structured() -> None:
    ai_call = SimpleNamespace(
        type="ai", content="surveying", tool_calls=[{"name": "gdelt_events", "args": {"query": "x"}}]
    )
    tool_msg = SimpleNamespace(type="tool", name="gdelt_events", content="429 rate limited")
    ai_final = SimpleNamespace(type="ai", content="done", tool_calls=[])
    chunks = [
        {"agent": {"messages": [ai_call]}},
        {"tools": {"messages": [tool_msg]}},
        {"agent": {"messages": [ai_final]}},
        {"generate_structured_response": {"structured_response": DiscoveryResult(notes="ok")}},
    ]
    ctx = _CapturingContext()
    out = stream_react_loop(_FakeStreamAgent(chunks), {"messages": []}, context=ctx, config=None)

    types = [t for t, _ in ctx.events]
    assert types.count("agent.step") == 2
    assert types.count("tool.result") == 1
    assert isinstance(out, DiscoveryResult)
    assert out.notes == "ok"


def test_cap_truncates_preserving_order() -> None:
    result = DiscoveryResult(candidates=_candidates(15), notes="n")
    capped = cap_candidates(result, 10)
    assert len(capped.candidates) == 10
    assert [c.title for c in capped.candidates] == [f"t{i}" for i in range(10)]
    assert capped.notes == "n"


def test_cap_handles_under_limit_and_zero() -> None:
    assert len(cap_candidates(DiscoveryResult(candidates=_candidates(3)), 10).candidates) == 3
    assert cap_candidates(DiscoveryResult(candidates=_candidates(3)), 0).candidates == []


def test_topic_candidate_defaults() -> None:
    c = TopicCandidate(title="x", why_notable="y")
    assert c.significance == "medium"
    assert c.suggested_route == "brief"
    assert c.seed_sources == []


def test_task_message_open_vs_goal() -> None:
    open_msg = build_task_message(None, 10)
    goal_msg = build_task_message("Russian economics", 5)
    assert "trending" in open_msg
    assert "up to 10" in open_msg
    assert "Russian economics" in goal_msg
    assert "up to 5" in goal_msg


def test_system_prompt_layers_present() -> None:
    assert "Algent agent" in SYSTEM_PROMPT  # universal base
    assert "discovery agent" in SYSTEM_PROMPT  # discovery class
    assert "general discovery agent" in SYSTEM_PROMPT  # specialty


def test_general_discovery_registered() -> None:
    spec = default_agent_registry().get("general_discovery")
    assert spec.family == "discovery"
    assert spec.runtime == "langgraph"
    assert spec.tool_ids == (GDELT_EVENTS_TOOL_ID, RSS_FEED_TOOL_ID, NEWS_FEEDS_TOOL_ID)


def test_discovery_tools_resolve_for_agent() -> None:
    resolved = default_tool_registry().resolve_for(general_spec.SPEC)
    ids = {spec.tool_id for spec in resolved}
    assert GDELT_EVENTS_TOOL_ID in ids
    assert RSS_FEED_TOOL_ID in ids
