"""
Runtime adapter interface.

This is Algent's runtime seam: a neutral contract that runtimes implement without
pulling LangGraph or any other rail framework into the core.
"""

from __future__ import annotations

from typing import Protocol

from algent_backend.agent_system.runs.context import AgentRunContext
from algent_backend.agent_system.runs.models import RunRequest, RunResult


class RuntimeAdapter(Protocol):
    """Executes an agent run through a specific runtime rail."""

    name: str

    def run(self, request: RunRequest, context: AgentRunContext) -> RunResult:
        """Execute ``request`` using services from ``context``."""
        ...
