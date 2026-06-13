"""
Shared agent-loop builder — a thin wrapper over LangGraph's prebuilt ReAct agent.

This is the one reusable tool-calling loop every agent stands on: a model with
tools bound, looping (model -> tool -> model) until the model stops calling tools
and returns. LangChain/LangGraph owns the loop, tool selection, and tool
execution; Algent supplies the model, the resolved tool menu, the composed system
prompt, and (optionally) a structured output schema.

Keeping the ``create_react_agent`` import confined here means agents express
*what* they are (prompt, tools, output shape) without each one re-importing the
rail. The exact prebuilt API is verified against the installed LangGraph; if it
shifts, this is the single place to adjust.
"""

from __future__ import annotations

from typing import Any


def build_react_loop(
    model: Any,
    tools: list[Any],
    *,
    system_prompt: str,
    response_format: Any | None = None,
) -> Any:
    """Build a compiled ReAct (tool-calling) agent graph.

    ``model`` is a LangChain chat model (from ``ResolvedModel.client``); ``tools``
    are concrete LangChain tools. When ``response_format`` is a Pydantic model,
    the agent emits a typed object on the ``structured_response`` state key.
    """
    from langgraph.prebuilt import create_react_agent

    return create_react_agent(
        model,
        tools,
        prompt=system_prompt,
        response_format=response_format,
    )
