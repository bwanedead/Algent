"""
LangGraph runtime adapter.

Executes the ``AgentSpec`` it is handed: builds the agent's graph, streams it
with the request input, and wraps the outcome in a ``RunResult``. It does not
know the agent catalog — agent lookup happens upstream in ``RunService``.

This is the rail boundary, so observability for the rail is wired here once for
every agent: the invocation config carries the Algent run id as LangSmith
run-name/metadata/tags (run-scoped traces), a usage callback rolls token totals
into the owned event stream, and ``max_turns`` maps to the rail's recursion
limit (the mechanical leash on agent loops).
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from algent_backend.agent_system.runs import events as ev
from algent_backend.agent_system.runs.context import AgentRunContext
from algent_backend.agent_system.runs.models import RunRequest, RunResult

if TYPE_CHECKING:
    from algent_backend.agent_system.agents.agent_spec import AgentSpec

# How much of a node's state update lands in the owned event stream. The full
# payloads live in the LangSmith trace; events keep a readable excerpt.
UPDATE_EXCERPT_MAX_CHARS = 4000


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
            output = self._execute(compiled, request, context, agent_spec)
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

    def _execute(
        self,
        compiled: Any,
        request: RunRequest,
        context: AgentRunContext,
        agent_spec: AgentSpec,
    ) -> dict[str, Any]:
        if not hasattr(compiled, "stream"):
            # Plain runnable (test fakes, simple builders): invoke without rail config.
            return compiled.invoke(request.input)

        config, usage_handler = self._invocation_config(request, context, agent_spec)
        final_state: dict[str, Any] = {}
        for mode, chunk in compiled.stream(
            request.input, config=config, stream_mode=["updates", "values"]
        ):
            if mode == "updates" and isinstance(chunk, dict):
                for node, update in chunk.items():
                    context.emit(
                        ev.NODE_COMPLETED,
                        {"node": node, "update": _excerpt(update)},
                    )
            elif mode == "values" and isinstance(chunk, dict):
                final_state = chunk

        self._emit_usage(context, usage_handler)
        return final_state

    def _invocation_config(
        self,
        request: RunRequest,
        context: AgentRunContext,
        agent_spec: AgentSpec,
    ) -> tuple[dict[str, Any], Any]:
        from langchain_core.callbacks import UsageMetadataCallbackHandler

        usage_handler = UsageMetadataCallbackHandler()
        config: dict[str, Any] = {
            # run_name carries the Algent run id so a LangSmith trace maps 1:1
            # back to the owned run record.
            "run_name": f"{agent_spec.agent_id}:{context.run_id}",
            "metadata": {
                "algent_run_id": context.run_id,
                "agent_id": agent_spec.agent_id,
                "family": agent_spec.family,
            },
            "tags": [agent_spec.agent_id],
            "callbacks": [usage_handler],
        }
        if request.max_turns is not None:
            config["recursion_limit"] = request.max_turns
        return config, usage_handler

    @staticmethod
    def _emit_usage(context: AgentRunContext, usage_handler: Any) -> None:
        for model_name, meta in (usage_handler.usage_metadata or {}).items():
            context.emit(
                ev.MODEL_USAGE,
                {
                    "model": model_name,
                    "input_tokens": meta.get("input_tokens"),
                    "output_tokens": meta.get("output_tokens"),
                    "total_tokens": meta.get("total_tokens"),
                },
            )


def _excerpt(value: object) -> str:
    text = str(value)
    if len(text) <= UPDATE_EXCERPT_MAX_CHARS:
        return text
    return text[:UPDATE_EXCERPT_MAX_CHARS] + f" ... [truncated, {len(text)} chars total]"
