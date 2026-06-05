"""
LangGraph runtime adapter.

Executes the ``AgentSpec`` it is handed: builds the agent's graph, invokes it
with the request input, and wraps the outcome in a ``RunResult``. It does not
know the agent catalog — agent lookup happens upstream in ``RunService``.

LangGraph itself is imported in ``agents/*/graph.py`` (which builds the graph),
not here: this adapter only relies on the rail's invocation contract, that
``build_graph(...)`` returns an object with ``.invoke(input)``.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from algent_backend.agent_system.runs.context import AgentRunContext
from algent_backend.agent_system.runs.models import RunRequest, RunResult

if TYPE_CHECKING:
    from algent_backend.agent_system.agents.agent_spec import AgentSpec


class LangGraphAdapter:
    """Executes agents through compiled LangGraph workflows."""

    name = "langgraph"

    def run(
        self,
        request: RunRequest,
        context: AgentRunContext,
        agent_spec: AgentSpec,
    ) -> RunResult:
        if agent_spec.runtime != self.name:
            return RunResult(
                run_id=context.run_id,
                agent_id=request.agent_id,
                runtime=self.name,
                status="failed",
                error=(
                    f"Agent '{agent_spec.agent_id}' targets runtime "
                    f"'{agent_spec.runtime}', not '{self.name}'."
                ),
            )

        try:
            compiled = agent_spec.build_graph(context)
            output = compiled.invoke(request.input)
            return RunResult(
                run_id=context.run_id,
                agent_id=request.agent_id,
                runtime=self.name,
                status="completed",
                output=dict(output),
            )
        except Exception as exc:
            return RunResult(
                run_id=context.run_id,
                agent_id=request.agent_id,
                runtime=self.name,
                status="failed",
                error=str(exc),
            )
