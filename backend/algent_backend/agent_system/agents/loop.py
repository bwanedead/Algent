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

from algent_backend.agent_system.foundation import cost
from algent_backend.agent_system.runs.events import AGENT_STEP, COST_LIMIT_REACHED, TOOL_RESULT

_STEP_EXCERPT_MAX_CHARS = 2000


def _usage_usd(msg: Any) -> float:
    """USD for an AI message from usage_metadata (0 if unknown). Does not charge."""
    usage = getattr(msg, "usage_metadata", None)
    if not isinstance(usage, dict):
        return 0.0
    return cost.estimate_usage_cost(cost.active_model(), usage)


def _excerpt(value: object) -> str:
    text = str(value)
    if len(text) <= _STEP_EXCERPT_MAX_CHARS:
        return text
    return text[:_STEP_EXCERPT_MAX_CHARS] + f" ... [truncated, {len(text)} chars total]"


def _emit_message_event(context: Any, msg: Any) -> None:
    """Emit a per-turn event for one streamed message. Best-effort: a trace hiccup
    must never break the run, so this never raises.
    """
    try:
        msg_type = getattr(msg, "type", None)
        if msg_type == "tool":
            context.emit(
                TOOL_RESULT,
                {"tool": getattr(msg, "name", None), "content": _excerpt(getattr(msg, "content", ""))},
            )
        elif msg_type == "ai":
            tool_calls = getattr(msg, "tool_calls", None) or []
            context.emit(
                AGENT_STEP,
                {
                    "content": _excerpt(getattr(msg, "content", "")),
                    "tool_calls": [
                        {"name": tc.get("name"), "args": tc.get("args")} for tc in tool_calls
                    ],
                },
            )
    except Exception:
        pass


def _turn_ceiling() -> float:
    return cost.estimate_model_call_ceiling(
        cost.active_model() or "gpt-5.4-mini",
        input_tokens=8_000,
        max_output_tokens=cost.DEFAULT_MAX_OUTPUT_TOKENS,
    )


def stream_react_loop(agent: Any, inputs: dict[str, Any], *, context: Any, config: Any) -> Any:
    """Run the compiled ReAct agent by streaming it, emitting a per-turn event for
    each model step and tool result so the run is watchable turn-by-turn.

    Returns the agent's ``structured_response`` (or ``None`` if it produced none).
    Streaming is how the loop executes; a genuine failure still propagates (and is
    captured to the run's audit trace) — only the per-event emission is best-effort.

    Each model turn is preauthorized via ``try_reserve`` against the article hard cap;
    usage settles the reservation. Hard-stop / failed reserve ends the loop.
    """
    if cost.is_hard_stop():
        context.emit(COST_LIMIT_REACHED, {"estimated_usd": cost.spent_usd(), "mode": cost.mode()})
        return None

    structured: Any = None
    pending = cost.try_reserve(_turn_ceiling(), op="model_turn")
    if pending is None and cost.is_active():
        context.emit(COST_LIMIT_REACHED, {"estimated_usd": cost.spent_usd(), "mode": cost.mode()})
        return None

    for chunk in agent.stream(inputs, config=config, stream_mode="updates"):
        if not isinstance(chunk, dict):
            continue
        stop = False
        for update in chunk.values():
            if not isinstance(update, dict):
                continue
            if "structured_response" in update:
                structured = update["structured_response"]
            for msg in update.get("messages") or []:
                if getattr(msg, "type", None) == "ai":
                    actual = _usage_usd(msg)
                    cost.settle(pending, actual)
                    pending = None
                    _emit_message_event(context, msg)
                    tool_calls = getattr(msg, "tool_calls", None) or []
                    if tool_calls:
                        pending = cost.try_reserve(_turn_ceiling(), op="model_turn")
                        if pending is None:
                            context.emit(
                                COST_LIMIT_REACHED,
                                {"estimated_usd": cost.spent_usd(), "mode": cost.mode()},
                            )
                            stop = True
                            break
                else:
                    _emit_message_event(context, msg)
            if stop:
                break
        if stop or cost.over_cap() or cost.is_hard_stop():
            if cost.over_cap() or cost.is_hard_stop():
                context.emit(COST_LIMIT_REACHED, {"estimated_usd": cost.spent_usd(), "mode": cost.mode()})
            break
    cost.release(pending)
    return structured


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
