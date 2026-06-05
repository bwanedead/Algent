"""
Hello workflow LangGraph definition.

``START -> generate_brief -> END``

The graph builder closes over ``AgentRunContext`` so nodes can resolve models
through Algent's ``ModelResolver`` without importing provider wrappers.
"""

from __future__ import annotations

from typing import Any, TypedDict

from langchain_core.messages import HumanMessage
from langgraph.graph import END, START, StateGraph
from langgraph.graph.state import CompiledStateGraph

from algent_backend.agent_system.runs.context import AgentRunContext

from .spec import DEFAULT_MODEL


class HelloState(TypedDict):
    topic: str
    brief: str | None


def _response_text(response: Any) -> str:
    content = getattr(response, "content", response)
    if isinstance(content, str):
        return content
    return str(content)


def build_graph(context: AgentRunContext) -> CompiledStateGraph[HelloState]:
    """Compile the hello workflow, closing over ``context`` for model access."""

    def generate_brief(state: HelloState) -> dict[str, str]:
        resolved = context.model_resolver.resolve(DEFAULT_MODEL)
        prompt = f"Write a one-sentence brief about: {state['topic']}"
        response = resolved.client.invoke([HumanMessage(content=prompt)])
        return {"brief": _response_text(response)}

    graph = StateGraph(HelloState)
    graph.add_node("generate_brief", generate_brief)
    graph.add_edge(START, "generate_brief")
    graph.add_edge("generate_brief", END)
    return graph.compile()
