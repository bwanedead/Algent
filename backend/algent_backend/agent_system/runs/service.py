"""
RunService — the orchestration entrypoint.

Owns the whole control path for a run: resolve the agent, resolve the runtime,
resolve and build the agent's tools, assemble the ``AgentRunContext``, hand the
resolved ``AgentSpec`` to the adapter, and keep the run's control-plane record
(state, events, timeline, ledger, result) in sync from start to terminal.

This module is allowed to import ``agents``, ``runtime``, ``tools``, and the
control plane because it orchestrates them. The neutral run primitives
(``runs/models.py``, ``runs/context.py``, ``runs/events.py``) must not — they
stay rail-, catalog-, and control-plane-agnostic.

Every run — including one that fails agent/runtime lookup — finishes with a
recorded terminal state and a ``done.json``, because external watchers poll for
that file. Failures become a failed ``RunResult``, never an escaped exception.
"""

from __future__ import annotations

from pathlib import Path
from uuid import uuid4

from algent_backend.agent_system.agents.registry import AgentRegistry, default_agent_registry
from algent_backend.agent_system.artifacts import ArtifactWriter
from algent_backend.agent_system.foundation.models import ModelResolver
from algent_backend.agent_system.runs import events as ev
from algent_backend.agent_system.runs.context import AgentRunContext
from algent_backend.agent_system.runs.control_plane import RunRecorder
from algent_backend.agent_system.runs.models import RunRequest, RunResult
from algent_backend.agent_system.runtime import RuntimeRegistry
from algent_backend.agent_system.tools import ResolvedTools, ToolRegistry, default_tool_registry


class RunService:
    """Orchestrates agent lookup, tool assembly, recording, and execution."""

    def __init__(
        self,
        agent_registry: AgentRegistry | None = None,
        runtime_registry: RuntimeRegistry | None = None,
        model_resolver: ModelResolver | None = None,
        tool_registry: ToolRegistry | None = None,
        runs_root: Path | None = None,
    ) -> None:
        self._agents = agent_registry or default_agent_registry()
        self._runtimes = runtime_registry or RuntimeRegistry()
        self._model_resolver = model_resolver or ModelResolver()
        self._tools = tool_registry or default_tool_registry()
        self._runs_root = runs_root

    def run(self, request: RunRequest) -> RunResult:
        run_id = request.run_id or str(uuid4())
        recorder = RunRecorder(run_id, self._runs_root)
        recorder.start(request)
        result = self._execute(request, run_id, recorder)
        recorder.finish(result)
        return result

    def _execute(self, request: RunRequest, run_id: str, recorder: RunRecorder) -> RunResult:
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
            emit=recorder.emit,
            artifacts=ArtifactWriter(
                recorder.paths.artifacts_dir, run_id, on_written=recorder.record_artifact
            ),
        )
        try:
            return adapter.run(request, context, agent_spec)
        except Exception as exc:  # adapters catch their own; this is the last net
            import traceback

            recorder.emit(
                ev.RUN_ERROR, {"error": str(exc), "traceback": traceback.format_exc()}
            )
            return self._failed(run_id, request, f"runtime adapter raised: {exc}")

    @staticmethod
    def _failed(run_id: str, request: RunRequest, error: str) -> RunResult:
        return RunResult(
            run_id=run_id,
            agent_id=request.agent_id,
            runtime=request.runtime,
            status="failed",
            error=error,
        )
