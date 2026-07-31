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
# Conservative chars→tokens (real English is ~4; use 3 so ceilings are upper bounds).
_CHARS_PER_TOKEN = 3
_MSG_FRAMING_TOKENS = 64


def estimate_text_tokens(text: str) -> int:
    """Upper-bound token estimate from raw text length."""
    return max(0, (len(text) + _CHARS_PER_TOKEN - 1) // _CHARS_PER_TOKEN)


def estimate_messages_tokens(messages: list[Any] | tuple[Any, ...] | None) -> int:
    """Conservative input-token estimate for a LangChain message list."""
    total_chars = 0
    for msg in messages or []:
        content = getattr(msg, "content", "") or ""
        if isinstance(content, list):
            parts: list[str] = []
            for part in content:
                if isinstance(part, dict):
                    parts.append(str(part.get("text", part)))
                else:
                    parts.append(str(part))
            content = "".join(parts)
        total_chars += len(str(content))
        for tc in getattr(msg, "tool_calls", None) or []:
            if isinstance(tc, dict):
                total_chars += len(str(tc.get("name", ""))) + len(str(tc.get("args", "")))
            else:
                total_chars += len(str(tc))
    return (
        max(0, (total_chars + _CHARS_PER_TOKEN - 1) // _CHARS_PER_TOKEN)
        + _MSG_FRAMING_TOKENS
    )


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
    """Emit a per-turn event for one streamed message. Best-effort: never raises."""
    try:
        msg_type = getattr(msg, "type", None)
        if msg_type == "tool":
            context.emit(
                TOOL_RESULT,
                {
                    "tool": getattr(msg, "name", None),
                    "content": _excerpt(getattr(msg, "content", "")),
                },
            )
        elif msg_type == "ai":
            tool_calls = getattr(msg, "tool_calls", None) or []
            context.emit(
                AGENT_STEP,
                {
                    "content": _excerpt(getattr(msg, "content", "")),
                    "tool_calls": [
                        {"name": tc.get("name"), "args": tc.get("args")}
                        for tc in tool_calls
                    ],
                },
            )
    except Exception:
        pass


def _emit_cost_limit(context: Any) -> None:
    context.emit(
        COST_LIMIT_REACHED,
        {"estimated_usd": cost.spent_usd(), "mode": cost.mode()},
    )


def turn_ceiling_usd(
    messages: list[Any] | tuple[Any, ...] | None,
    *,
    model: str | None = None,
    max_output_tokens: int | None = None,
) -> float:
    """Conservative USD upper bound for one model turn given the current input messages."""
    max_out = (
        cost.DEFAULT_MAX_OUTPUT_TOKENS
        if max_output_tokens is None
        else max(0, int(max_output_tokens))
    )
    return cost.estimate_model_call_ceiling(
        model or cost.active_model() or "gpt-5.4-mini",
        input_tokens=estimate_messages_tokens(messages),
        max_output_tokens=max_out,
    )


def _bind_max_output(model: Any, max_output_tokens: int) -> Any:
    """Attach an explicit output-token ceiling when the client supports it."""
    for kwargs in (
        {"max_tokens": max_output_tokens},
        {"max_completion_tokens": max_output_tokens},
        {"max_output_tokens": max_output_tokens},
    ):
        bind = getattr(model, "bind", None)
        if not callable(bind):
            return model
        try:
            return bind(**kwargs)
        except Exception:  # noqa: BLE001 — try next kw; fall through unbound
            continue
    return model


def _handle_ai_turn(
    context: Any,
    msg: Any,
    *,
    pending: Any,
    seen: list[Any],
    essential: bool,
    max_out: int,
) -> tuple[Any, bool]:
    """Settle one AI message and optionally reserve the next turn. Returns (pending, stop)."""
    cost.settle(pending, _usage_usd(msg))
    _emit_message_event(context, msg)
    if cost.is_hard_stop():
        _emit_cost_limit(context)
        return None, True
    if not getattr(msg, "tool_calls", None):
        return None, False
    nxt = cost.try_reserve(
        turn_ceiling_usd(seen, max_output_tokens=max_out),
        op="model_turn",
        essential=essential,
    )
    if nxt is None:
        _emit_cost_limit(context)
        return None, True
    return nxt, False


def _process_stream_update(
    update: dict[str, Any],
    *,
    context: Any,
    seen: list[Any],
    pending: Any,
    essential: bool,
    max_out: int,
    structured: Any,
) -> tuple[Any, Any, bool]:
    """Process one stream update dict. Returns (structured, pending, stop)."""
    if "structured_response" in update:
        structured = update["structured_response"]
    stop = False
    for msg in update.get("messages") or []:
        seen.append(msg)
        if getattr(msg, "type", None) == "ai":
            pending, stop = _handle_ai_turn(
                context, msg, pending=pending, seen=seen,
                essential=essential, max_out=max_out,
            )
        else:
            _emit_message_event(context, msg)
        if stop:
            break
    return structured, pending, stop


def _consume_stream_updates(
    agent: Any,
    inputs: dict[str, Any],
    *,
    context: Any,
    config: Any,
    seen: list[Any],
    pending: Any,
    essential: bool,
    max_out: int,
) -> tuple[Any, Any]:
    """Drive the agent stream; return (structured_response, leftover_pending)."""
    structured: Any = None
    for chunk in agent.stream(inputs, config=config, stream_mode="updates"):
        if not isinstance(chunk, dict):
            continue
        stop = False
        for update in chunk.values():
            if not isinstance(update, dict):
                continue
            structured, pending, stop = _process_stream_update(
                update, context=context, seen=seen, pending=pending,
                essential=essential, max_out=max_out, structured=structured,
            )
            if stop:
                break
        if stop or cost.over_cap() or cost.is_hard_stop():
            if cost.over_cap() or cost.is_hard_stop():
                _emit_cost_limit(context)
            break
    return structured, pending


def stream_react_loop(
    agent: Any,
    inputs: dict[str, Any],
    *,
    context: Any,
    config: Any,
    essential: bool = False,
    max_output_tokens: int | None = None,
) -> Any:
    """Run the compiled ReAct agent by streaming it, emitting per-turn events.

    Each model turn is preauthorized via ``try_reserve`` using a ceiling from the
    *actual* message corpus + ``max_output_tokens``. Settling above the reservation
    hard-stops the article budget (see ``cost.settle``).
    """
    if cost.is_hard_stop():
        _emit_cost_limit(context)
        return None

    max_out = (
        cost.DEFAULT_MAX_OUTPUT_TOKENS
        if max_output_tokens is None
        else max(0, int(max_output_tokens))
    )
    seen: list[Any] = list(inputs.get("messages") or [])
    pending = cost.try_reserve(
        turn_ceiling_usd(seen, max_output_tokens=max_out),
        op="model_turn",
        essential=essential,
    )
    if pending is None and cost.is_active():
        _emit_cost_limit(context)
        return None

    structured, pending = _consume_stream_updates(
        agent, inputs, context=context, config=config, seen=seen,
        pending=pending, essential=essential, max_out=max_out,
    )
    cost.release(pending)
    return structured


def _tool_error_to_message(exc: Exception) -> str:
    """Turn a tool exception into a message the agent can recover from."""
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
    max_output_tokens: int | None = None,
) -> Any:
    """Build a compiled ReAct (tool-calling) agent graph.

    ``max_output_tokens`` is bound onto the model when supported so the reserved
    ceiling matches the provider limit used for generation.
    """
    from langgraph.prebuilt import ToolNode, create_react_agent

    max_out = (
        cost.DEFAULT_MAX_OUTPUT_TOKENS
        if max_output_tokens is None
        else max(0, int(max_output_tokens))
    )
    bound = _bind_max_output(model, max_out)
    tool_node = ToolNode(tools, handle_tool_errors=_tool_error_to_message)
    return create_react_agent(
        bound,
        tool_node,
        prompt=system_prompt,
        response_format=response_format,
    )
