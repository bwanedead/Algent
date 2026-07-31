"""
Shared agent-loop builder — a thin wrapper over LangGraph's prebuilt ReAct agent.

Cost authorization lives at the chat-model invocation boundary
(``foundation.models.budget_gate``): every provider call — including LangGraph's
post-loop ``generate_structured_response`` — is reserved before it begins.
This module streams the agent for observability and stops cleanly on budget refusal.
"""

from __future__ import annotations

from typing import Any

from algent_backend.agent_system.foundation import cost
from algent_backend.agent_system.foundation.models.budget_gate import (
    BudgetRefusedError,
    estimate_invoke_ceiling_usd,
    estimate_messages_tokens,
    estimate_payload_tokens,
    estimate_text_tokens,
    gate_chat_model,
    turn_essential_scope,
)
from algent_backend.agent_system.runs.events import AGENT_STEP, COST_LIMIT_REACHED, TOOL_RESULT

_STEP_EXCERPT_MAX_CHARS = 2000

# Re-export estimators for tests / callers that previously imported them from here.
__all__ = [
    "build_react_loop",
    "stream_react_loop",
    "estimate_messages_tokens",
    "estimate_payload_tokens",
    "estimate_text_tokens",
    "estimate_invoke_ceiling_usd",
    "turn_ceiling_usd",
    "BudgetRefusedError",
]


def turn_ceiling_usd(
    messages: list[Any] | tuple[Any, ...] | None,
    *,
    model: str | None = None,
    max_output_tokens: int | None = None,
    tools: Any = None,
    response_schema: Any = None,
) -> float:
    """Conservative USD upper bound for one model call (full payload when given)."""
    return estimate_invoke_ceiling_usd(
        messages,
        model=model,
        max_output_tokens=max_output_tokens,
        tools=tools,
        response_schema=response_schema,
    )


def _excerpt(value: object) -> str:
    text = str(value)
    if len(text) <= _STEP_EXCERPT_MAX_CHARS:
        return text
    return text[:_STEP_EXCERPT_MAX_CHARS] + f" ... [truncated, {len(text)} chars total]"


def _emit_message_event(context: Any, msg: Any) -> None:
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


def _process_stream_update(
    update: dict[str, Any], *, context: Any, structured: Any,
) -> tuple[Any, bool]:
    """Returns (structured, stop)."""
    if "structured_response" in update:
        structured = update["structured_response"]
    for msg in update.get("messages") or []:
        _emit_message_event(context, msg)
    if cost.is_hard_stop() or cost.over_cap():
        _emit_cost_limit(context)
        return structured, True
    return structured, False


def stream_react_loop(
    agent: Any,
    inputs: dict[str, Any],
    *,
    context: Any,
    config: Any,
    essential: bool = False,
    max_output_tokens: int | None = None,  # noqa: ARG001 — kept for call-site compat
) -> Any:
    """Stream the ReAct agent; metering is enforced inside the gated chat model.

    ``essential=True`` marks *model turns* as finish-path (via the budget gate's
    turn-essential override / ``BudgetGatedChatModel.essential``). Nested tool
    calls do not inherit that flag — they must not use ``cost.essential_scope``.
    """
    if cost.is_hard_stop():
        _emit_cost_limit(context)
        return None

    structured: Any = None
    try:
        with turn_essential_scope(essential):
            for chunk in agent.stream(inputs, config=config, stream_mode="updates"):
                if not isinstance(chunk, dict):
                    continue
                stop = False
                for update in chunk.values():
                    if not isinstance(update, dict):
                        continue
                    structured, stop = _process_stream_update(
                        update, context=context, structured=structured,
                    )
                    if stop:
                        break
                if stop:
                    break
    except BudgetRefusedError:
        _emit_cost_limit(context)
    return structured


def _tool_error_to_message(exc: Exception) -> str:
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
    essential: bool = False,
) -> Any:
    """Build a compiled ReAct agent with a budget-gated chat model."""
    from langgraph.prebuilt import ToolNode, create_react_agent

    max_out = (
        cost.DEFAULT_MAX_OUTPUT_TOKENS
        if max_output_tokens is None
        else max(0, int(max_output_tokens))
    )
    gated = gate_chat_model(model, max_output_tokens=max_out, essential=essential)
    # Bind output ceiling on the gated model so Binding.bound stays BudgetGatedChatModel
    # (LangGraph ``_get_model`` unwraps Binding → bound for structured-response calls).
    try:
        gated = gated.bind(max_tokens=max_out)
    except Exception:  # noqa: BLE001
        try:
            gated = gated.bind(max_completion_tokens=max_out)
        except Exception:  # noqa: BLE001
            pass

    tool_node = ToolNode(tools, handle_tool_errors=_tool_error_to_message)
    return create_react_agent(
        gated,
        tool_node,
        prompt=system_prompt,
        response_format=response_format,
    )
