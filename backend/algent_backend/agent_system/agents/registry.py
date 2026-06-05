"""
AgentRegistry — the known agent catalog.

A small, explicit in-memory map of ``agent_id`` to ``AgentSpec``. No dynamic
discovery, plugin system, or filesystem scanning — agents are registered in code.

``get`` raises ``ValueError`` for an unknown agent, mirroring
``RuntimeRegistry.get``. The orchestration layer (``RunService``) catches that
and returns a failed ``RunResult`` rather than letting the exception escape.
"""

from __future__ import annotations

from .agent_spec import AgentSpec


class AgentRegistry:
    """Selects an ``AgentSpec`` by id."""

    def __init__(self) -> None:
        self._agents: dict[str, AgentSpec] = {}

    def register(self, spec: AgentSpec) -> None:
        self._agents[spec.agent_id] = spec

    def get(self, agent_id: str) -> AgentSpec:
        spec = self._agents.get(agent_id)
        if spec is None:
            known = ", ".join(sorted(self._agents)) or "(none)"
            raise ValueError(f"Unknown agent '{agent_id}'. Known agents: {known}.")
        return spec

    def list(self) -> list[AgentSpec]:
        return list(self._agents.values())


def default_agent_registry() -> AgentRegistry:
    """Build the registry with the agents Algent ships by default."""
    # Imported lazily so merely importing the registry class does not pull an
    # agent's graph module (and its LangGraph imports) into memory.
    from .hello_workflow.spec import SPEC as hello_workflow_spec

    registry = AgentRegistry()
    registry.register(hello_workflow_spec)
    return registry
