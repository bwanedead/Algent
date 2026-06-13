"""
The discovery loop — wraps the shared ReAct loop with discovery I/O.

The agent's tool-calling loop is LangGraph's prebuilt ReAct agent; this builder
wraps it in a thin graph so discovery's input (an optional goal + a candidate
cap) and output (a ``DiscoveryResult`` artifact) match Algent's run conventions
instead of raw chat messages.

Run input (graph state): ``goal`` (optional focus; absent = open survey) and
``max_candidates``. Run output: ``result`` (a serialized ``DiscoveryResult``),
also written as an artifact. The candidate cap is enforced mechanically after the
model returns — discipline serving the model's authorship, not replacing it.

LangGraph/LangChain imports live here and in ``agents/loop.py``; the agent's
``spec.py`` stays rail-free.
"""

from __future__ import annotations

from typing import Any, TypedDict

from langchain_core.messages import HumanMessage
from langchain_core.runnables import RunnableConfig
from langgraph.graph import END, START, StateGraph

from algent_backend.agent_system.agents.loop import build_react_loop
from algent_backend.agent_system.foundation.models import ModelSpec
from algent_backend.agent_system.runs.context import AgentRunContext

from .contracts import DiscoveryResult, cap_candidates

DEFAULT_MAX_CANDIDATES = 10
ARTIFACT_NAME = "discovery_result.json"
DISCOVERY_COMPLETED = "discovery.completed"


class DiscoveryState(TypedDict, total=False):
    goal: str | None
    max_candidates: int
    result: dict[str, Any]


def _initial_message(goal: str | None, cap: int) -> str:
    """The task message that seeds the discovery loop."""
    if goal:
        focus = f"Focus your discovery on this goal: {goal}\n\n"
    else:
        focus = (
            "Survey broadly for notable, interesting, or significant items that "
            "could be worth deeper coverage.\n\n"
        )
    return (
        f"{focus}"
        "Use your discovery tools to look at what is actually being reported, "
        f"then return up to {cap} candidate topics worth deeper investigation. "
        "Be selective and ground each candidate in sources you found. Returning "
        "fewer (or none) is fine if little clears the bar."
    )


def build_discovery_graph(
    context: AgentRunContext,
    *,
    model_spec: ModelSpec,
    tool_ids: tuple[str, ...],
    system_prompt: str,
    max_candidates_default: int = DEFAULT_MAX_CANDIDATES,
) -> Any:
    """Compile the discovery graph for an agent's model, tools, and prompt."""
    model = context.model_resolver.resolve(model_spec).client
    tools = [context.tools[tool_id] for tool_id in tool_ids]
    agent = build_react_loop(
        model, tools, system_prompt=system_prompt, response_format=DiscoveryResult
    )

    def research(state: DiscoveryState, config: RunnableConfig) -> dict[str, Any]:
        cap = state.get("max_candidates") or max_candidates_default
        goal = state.get("goal")

        # Pass config through so the inner loop inherits the run's tracing,
        # usage callbacks, and turn budget from the adapter.
        agent_out = agent.invoke(
            {"messages": [HumanMessage(content=_initial_message(goal, cap))]}, config
        )
        produced = agent_out.get("structured_response")
        result = produced if isinstance(produced, DiscoveryResult) else DiscoveryResult()
        result = cap_candidates(result, cap)

        if context.artifacts is not None:
            context.artifacts.write_json(ARTIFACT_NAME, result.model_dump())
        context.emit(
            DISCOVERY_COMPLETED,
            {"candidate_count": len(result.candidates), "goal": goal},
        )
        return {"result": result.model_dump()}

    graph = StateGraph(DiscoveryState)
    graph.add_node("research", research)
    graph.add_edge(START, "research")
    graph.add_edge("research", END)
    return graph.compile()
