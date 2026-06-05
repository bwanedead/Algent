"""
RunService — the orchestration entrypoint.

Resolves the agent and the runtime, then hands the resolved ``AgentSpec`` to the
adapter. This is the single control point: agent lookup happens here, before the
runtime executes, so runtime adapters never need to know the agent catalog.

This module is allowed to import ``agents`` and ``runtime`` because it
orchestrates both. The neutral run primitives (``runs/models.py``,
``runs/context.py``) must not — they stay rail- and catalog-agnostic.

Lookup failures (unknown agent, unknown runtime) are turned into a failed
``RunResult`` rather than raised, since this is the user-facing entrypoint. The
agent's declared runtime is enforced by the adapter (it fails a mismatched spec).
"""

from __future__ import annotations

from algent_backend.agent_system.agents.registry import AgentRegistry, default_agent_registry
from algent_backend.agent_system.runs.context import AgentRunContext
from algent_backend.agent_system.runs.models import RunRequest, RunResult
from algent_backend.agent_system.runtime import RuntimeRegistry


class RunService:
    """Orchestrates agent lookup and runtime execution."""

    def __init__(
        self,
        agent_registry: AgentRegistry | None = None,
        runtime_registry: RuntimeRegistry | None = None,
    ) -> None:
        self._agents = agent_registry or default_agent_registry()
        self._runtimes = runtime_registry or RuntimeRegistry()

    def run(self, request: RunRequest, context: AgentRunContext) -> RunResult:
        try:
            agent_spec = self._agents.get(request.agent_id)
        except ValueError as exc:
            return self._failed(request, context, str(exc))

        try:
            adapter = self._runtimes.get(request.runtime)
        except ValueError as exc:
            return self._failed(request, context, str(exc))

        return adapter.run(request, context, agent_spec)

    @staticmethod
    def _failed(request: RunRequest, context: AgentRunContext, error: str) -> RunResult:
        return RunResult(
            run_id=context.run_id,
            agent_id=request.agent_id,
            runtime=request.runtime,
            status="failed",
            error=error,
        )
