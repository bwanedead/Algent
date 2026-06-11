"""
ToolRegistry — the known tool catalog and scope resolution.

Explicit, in-code registration (no discovery). ``resolve_for`` decides which
tools an agent may use by matching the scope hierarchy — global, then the agent's
family, then the agent itself — plus any tools the agent names explicitly in
``tool_ids``.

This module stays neutral: it imports no LangChain/LangGraph, and ``AgentSpec``
only under ``TYPE_CHECKING``.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from .spec import GLOBAL_SCOPE, ToolSpec, agent_scope, family_scope

if TYPE_CHECKING:
    from algent_backend.agent_system.agents.agent_spec import AgentSpec


class ToolRegistry:
    """Selects tools available to an agent."""

    def __init__(self) -> None:
        self._tools: dict[str, ToolSpec] = {}

    def register(self, spec: ToolSpec) -> None:
        self._tools[spec.tool_id] = spec

    def get(self, tool_id: str) -> ToolSpec:
        spec = self._tools.get(tool_id)
        if spec is None:
            known = ", ".join(sorted(self._tools)) or "(none)"
            raise ValueError(f"Unknown tool '{tool_id}'. Known tools: {known}.")
        return spec

    def list(self) -> list[ToolSpec]:
        return list(self._tools.values())

    def resolve_for(self, agent_spec: AgentSpec) -> list[ToolSpec]:
        """Return the tool specs an agent may use, by scope or explicit id.

        Explicitly required tools (``agent_spec.tool_ids``) must exist; a missing
        one is a configuration error and raises ``ValueError`` rather than failing
        later with an opaque missing-key error inside the graph.
        """
        wanted_ids = set(agent_spec.tool_ids)
        missing = wanted_ids - set(self._tools)
        if missing:
            names = ", ".join(sorted(missing))
            raise ValueError(
                f"Unknown required tool(s) '{names}' for agent '{agent_spec.agent_id}'."
            )

        scopes = {GLOBAL_SCOPE, agent_scope(agent_spec.agent_id)}
        if agent_spec.family:
            scopes.add(family_scope(agent_spec.family))

        return [
            spec
            for spec in self._tools.values()
            if spec.scope in scopes or spec.tool_id in wanted_ids
        ]


def default_tool_registry() -> ToolRegistry:
    """Build the registry with the tools Algent ships by default."""
    # Imported lazily so importing the registry does not pull a tool's
    # third-party dependencies (e.g. langchain_tavily) into memory.
    from .sourcing import sourcing_tool_specs

    registry = ToolRegistry()
    for spec in sourcing_tool_specs():
        registry.register(spec)
    return registry
