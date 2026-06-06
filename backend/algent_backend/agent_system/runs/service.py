"""
RunService — the orchestration entrypoint.

Owns the whole control path for a run: resolve the agent, resolve the runtime,
resolve and build the agent's tools, assemble the ``AgentRunContext``, then hand
the resolved ``AgentSpec`` to the adapter. Agent lookup happens here, before the
runtime executes, so runtime adapters never need to know the agent catalog.

This module is allowed to import ``agents``, ``runtime``, and ``tools`` because it
orchestrates them. The neutral run primitives (``runs/models.py``,
``runs/context.py``) must not — they stay rail-, catalog-, and tool-agnostic.

Lookup failures (unknown agent, unknown runtime) are turned into a failed
``RunResult`` rather than raised, since this is the user-facing entrypoint. The
agent's declared runtime is enforced by the adapter (it fails a mismatched spec).
"""

from __future__ import annotations

from uuid import uuid4

from algent_backend.agent_system.agents.registry import AgentRegistry, default_agent_registry
from algent_backend.agent_system.foundation.models import ModelResolver
from algent_backend.agent_system.runs.context import AgentRunContext
from algent_backend.agent_system.runs.models import RunRequest, RunResult
from algent_backend.agent_system.runtime import RuntimeRegistry
from algent_backend.agent_system.tools import ResolvedTools, ToolRegistry, default_tool_registry


class RunService:
    """Orchestrates agent lookup, tool assembly, and runtime execution."""

    def __init__(
        self,
        agent_registry: AgentRegistry | None = None,
        runtime_registry: RuntimeRegistry | None = None,
        model_resolver: ModelResolver | None = None,
        tool_registry: ToolRegistry | None = None,
    ) -> None:
        self._agents = agent_registry or default_agent_registry()
        self._runtimes = runtime_registry or RuntimeRegistry()
        self._model_resolver = model_resolver or ModelResolver()
        self._tools = tool_registry or default_tool_registry()

    def run(self, request: RunRequest) -> RunResult:
        run_id = str(uuid4())

        try:
            agent_spec = self._agents.get(request.agent_id)
        except ValueError as exc:
            return self._failed(run_id, request, str(exc))

        try:
            adapter = self._runtimes.get(request.runtime)
        except ValueError as exc:
            return self._failed(run_id, request, str(exc))

        try:
            resolved = self._tools.resolve_for(agent_spec)
        except ValueError as exc:
            return self._failed(run_id, request, str(exc))

        context = AgentRunContext(
            run_id=run_id,
            model_resolver=self._model_resolver,
            # Lazy: tools resolve as available but only build when a node uses them.
            tools=ResolvedTools(resolved),
        )
        return adapter.run(request, context, agent_spec)

    @staticmethod
    def _failed(run_id: str, request: RunRequest, error: str) -> RunResult:
        return RunResult(
            run_id=run_id,
            agent_id=request.agent_id,
            runtime=request.runtime,
            status="failed",
            error=error,
        )
