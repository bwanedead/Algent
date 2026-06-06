"""
Tests for the tool layer: ToolSpec scoping and ToolRegistry resolution.

Offline — fake tool builders, no real LangChain/Tavily.
"""

from __future__ import annotations

import pytest

from algent_backend.agent_system.agents.agent_spec import AgentSpec
from algent_backend.agent_system.tools import (
    GLOBAL_SCOPE,
    ResolvedTools,
    ToolRegistry,
    ToolSpec,
    agent_scope,
    family_scope,
)


def _tool(tool_id: str, scope: str) -> ToolSpec:
    return ToolSpec(
        tool_id=tool_id,
        name=tool_id,
        description="",
        scope=scope,
        build=lambda: object(),
    )


def _agent(
    agent_id: str = "a",
    family: str | None = None,
    tool_ids: tuple[str, ...] = (),
) -> AgentSpec:
    return AgentSpec(
        agent_id=agent_id,
        name=agent_id,
        runtime="langgraph",
        build_graph=lambda _context: None,
        family=family,
        tool_ids=tool_ids,
    )


def _ids(specs: list[ToolSpec]) -> set[str]:
    return {s.tool_id for s in specs}


def test_global_tool_resolves_for_any_agent() -> None:
    registry = ToolRegistry()
    registry.register(_tool("web_search", "global"))
    assert _ids(registry.resolve_for(_agent())) == {"web_search"}


def test_family_tool_resolves_only_for_matching_family() -> None:
    registry = ToolRegistry()
    registry.register(_tool("rss", family_scope("news")))

    assert _ids(registry.resolve_for(_agent(family="news"))) == {"rss"}
    assert _ids(registry.resolve_for(_agent(family="finance"))) == set()
    assert _ids(registry.resolve_for(_agent(family=None))) == set()


def test_agent_scoped_tool_resolves_only_for_that_agent() -> None:
    registry = ToolRegistry()
    registry.register(_tool("special", agent_scope("news_brief")))

    assert _ids(registry.resolve_for(_agent(agent_id="news_brief"))) == {"special"}
    assert _ids(registry.resolve_for(_agent(agent_id="other"))) == set()


def test_explicit_tool_ids_include_out_of_scope_tool() -> None:
    registry = ToolRegistry()
    registry.register(_tool("special", agent_scope("someone_else")))

    # Out of scope by scope, but named explicitly -> included.
    resolved = registry.resolve_for(_agent(agent_id="me", tool_ids=("special",)))
    assert _ids(resolved) == {"special"}


def test_get_unknown_tool_raises() -> None:
    with pytest.raises(ValueError, match="Unknown tool"):
        ToolRegistry().get("nope")


def test_resolve_for_raises_on_unknown_required_tool() -> None:
    registry = ToolRegistry()  # empty
    with pytest.raises(ValueError, match="Unknown required tool"):
        registry.resolve_for(_agent(agent_id="news_brief", tool_ids=("web_search",)))


def test_resolved_tools_build_lazily_and_cache() -> None:
    builds = {"count": 0}

    def _builder() -> object:
        builds["count"] += 1
        return object()

    spec = ToolSpec(
        tool_id="web_search",
        name="Web Search",
        description="",
        scope=GLOBAL_SCOPE,
        build=_builder,
    )
    tools = ResolvedTools([spec])

    # Available without building.
    assert "web_search" in tools
    assert builds["count"] == 0

    # Built on first access, cached thereafter.
    first = tools["web_search"]
    second = tools["web_search"]
    assert first is second
    assert builds["count"] == 1
