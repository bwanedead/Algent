"""
News brief LangGraph definition.

``START -> research_and_brief -> END``

v0 uses deterministic orchestration: the node explicitly searches, then asks the
model to write the brief. It does not let the model decide whether/when to search
(no ``bind_tools``). That keeps editorial behaviour predictable and is the right
base for later perspective-balanced search planning.

The graph builder takes the model spec as a parameter so ``spec.py`` can import
this module without a cycle, and closes over ``AgentRunContext`` for both the
model resolver and the resolved tools.
"""

from __future__ import annotations

from typing import Any, TypedDict

from langchain_core.messages import HumanMessage, SystemMessage
from langgraph.graph import END, START, StateGraph
from langgraph.graph.state import CompiledStateGraph

from algent_backend.agent_system.foundation.models import ModelSpec
from algent_backend.agent_system.runs.context import AgentRunContext
from algent_backend.agent_system.tools.sourcing.search.tavily import WEB_SEARCH_TOOL_ID

from . import prompts


class NewsBriefState(TypedDict):
    topic: str
    search_results: Any
    brief: str | None


def _response_text(response: Any) -> str:
    content = getattr(response, "content", response)
    if isinstance(content, str):
        return content
    return str(content)


def _format_results(results: Any) -> str:
    """Render search results into prompt text, tolerant of shape."""
    if isinstance(results, dict):
        items = results.get("results", [])
    elif isinstance(results, list):
        items = results
    else:
        return str(results)

    lines: list[str] = []
    for item in items:
        if isinstance(item, dict):
            title = item.get("title", "")
            content = item.get("content", "")
            url = item.get("url", "")
            lines.append(f"- {title}\n  {content}\n  ({url})")
        else:
            lines.append(f"- {item}")
    return "\n".join(lines) if lines else str(results)


def build_graph(
    context: AgentRunContext, model_spec: ModelSpec
) -> CompiledStateGraph[NewsBriefState]:
    """Compile the news brief workflow, closing over ``context``."""

    def research_and_brief(state: NewsBriefState) -> dict[str, Any]:
        topic = state["topic"]

        search_tool = context.tools[WEB_SEARCH_TOOL_ID]
        search_results = search_tool.invoke({"query": topic})

        resolved = context.model_resolver.resolve(model_spec)
        messages = [
            SystemMessage(content=prompts.SYSTEM_PROMPT),
            HumanMessage(content=prompts.build_user_prompt(topic, _format_results(search_results))),
        ]
        response = resolved.client.invoke(messages)

        return {"search_results": search_results, "brief": _response_text(response)}

    graph = StateGraph(NewsBriefState)
    graph.add_node("research_and_brief", research_and_brief)
    graph.add_edge(START, "research_and_brief")
    graph.add_edge("research_and_brief", END)
    return graph.compile()
