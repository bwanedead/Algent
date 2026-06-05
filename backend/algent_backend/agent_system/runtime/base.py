"""
Runtime adapter interface.

This is Algent's runtime seam: a neutral contract that runtimes implement without
pulling LangGraph or any other rail framework into the core. The adapter receives
an already-resolved ``AgentSpec`` — it does not look agents up itself.

``AgentSpec`` is imported only under ``TYPE_CHECKING`` so this neutral layer never
pulls the agents package (and its rail imports) at runtime.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Protocol

from algent_backend.agent_system.runs.context import AgentRunContext
from algent_backend.agent_system.runs.models import RunRequest, RunResult

if TYPE_CHECKING:
    from algent_backend.agent_system.agents.agent_spec import AgentSpec


class RuntimeAdapter(Protocol):
    """Executes a resolved agent through a specific runtime rail."""

    name: str

    def run(
        self,
        request: RunRequest,
        context: AgentRunContext,
        agent_spec: AgentSpec,
    ) -> RunResult:
        """Execute ``agent_spec`` using services from ``context``."""
        ...
