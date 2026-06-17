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


def _tool_error_to_message(exc: Exception) -> str:
    """Turn a tool exception into a message the agent can recover from.

    Agent ergonomics: a tool failure (rate limit, network, bad args) is a *result*
    the model reads and routes around — it must never crash the whole run.
    LangGraph's default ToolNode re-raises, so we supply this handler instead.
    """
    return (
        f"This tool call failed with an error: {exc}. "
        "Do not repeat the same call unchanged — try a different query or a "
        "different tool, or proceed with what you already have."
    )


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

    Tools are wrapped in a ``ToolNode`` that converts any tool exception into a
    tool message (instead of LangGraph's default re-raise) so one flaky tool —
    e.g. a rate-limited source — can never crash the whole run; the agent sees
    the error and routes around it.
    """
    from langgraph.prebuilt import ToolNode, create_react_agent

    tool_node = ToolNode(tools, handle_tool_errors=_tool_error_to_message)
    return create_react_agent(
        model,
        tool_node,
        prompt=system_prompt,
        response_format=response_format,
    )
