"""
LangGraph runtime adapter.

Receives neutral run contracts, locates the agent graph builder, compiles and
invokes the graph, and wraps the outcome in a ``RunResult``. LangGraph imports
live here and in ``agents/*/graph.py`` — not in the neutral run or base layers.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

from langgraph.graph.state import CompiledStateGraph

from algent_backend.agent_system.agents.hello_workflow import graph as hello_workflow_graph
from algent_backend.agent_system.agents.hello_workflow import spec as hello_workflow_spec
from algent_backend.agent_system.runs.context import AgentRunContext
from algent_backend.agent_system.runs.models import RunRequest, RunResult

GraphBuilder = Callable[[AgentRunContext], CompiledStateGraph[Any]]

# Explicit agent map for Slice 1 — no discovery or dynamic loading yet.
_AGENT_BUILDERS: dict[str, GraphBuilder] = {
    hello_workflow_spec.AGENT_ID: hello_workflow_graph.build_graph,
}


class LangGraphAdapter:
    """Executes agents through compiled LangGraph workflows."""

    name = "langgraph"

    def run(self, request: RunRequest, context: AgentRunContext) -> RunResult:
        builder = _AGENT_BUILDERS.get(request.agent_id)
        if builder is None:
            return RunResult(
                run_id=context.run_id,
                agent_id=request.agent_id,
                runtime=self.name,
                status="failed",
                error=f"Unknown agent '{request.agent_id}'.",
            )

        try:
            compiled = builder(context)
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
