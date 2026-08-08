"""
Budget gate at the chat-model invocation boundary.

Every provider call — ReAct turns, LangGraph ``generate_structured_response`` /
``with_structured_output``, and direct structured one-shots — must ``try_reserve``
against a ceiling estimated from the *complete* request payload (messages + tool
schemas + response schema) before the network call begins.
"""

from __future__ import annotations

import contextvars
import json
from collections.abc import Iterator, Sequence
from contextlib import contextmanager
from typing import Any

from langchain_core.callbacks import CallbackManagerForLLMRun
from langchain_core.language_models.chat_models import BaseChatModel
from langchain_core.messages import AIMessage, BaseMessage
from langchain_core.outputs import ChatGeneration, ChatGenerationChunk, ChatResult
from langchain_core.runnables import Runnable
from pydantic import ConfigDict, Field

from algent_backend.agent_system.foundation import cost
from algent_backend.agent_system.foundation.text_hygiene import scrub

_CHARS_PER_TOKEN = 3
_MSG_FRAMING_TOKENS = 64

# Turn-only essential override for stream_react_loop(essential=True). Unlike
# cost.essential_scope, this is read only by BudgetGatedChatModel — tools that
# call try_reserve() without an explicit flag stay non-essential under slim.
_turn_essential: contextvars.ContextVar[bool] = contextvars.ContextVar(
    "budget_gate_turn_essential", default=False,
)


class BudgetRefusedError(RuntimeError):
    """Raised when a model call may not begin under the active article budget."""


@contextmanager
def turn_essential_scope(active: bool = True) -> Iterator[None]:
    """Mark gated model turns as essential for the duration of the block."""
    token = _turn_essential.set(bool(active))
    try:
        yield
    finally:
        _turn_essential.reset(token)


def estimate_text_tokens(text: str) -> int:
    return max(0, (len(text) + _CHARS_PER_TOKEN - 1) // _CHARS_PER_TOKEN)


def _jsonish(value: Any) -> str:
    try:
        return json.dumps(value, default=str, sort_keys=True)
    except TypeError:
        return str(value)


def estimate_messages_tokens(messages: Sequence[Any] | None) -> int:
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
    return max(0, (total_chars + _CHARS_PER_TOKEN - 1) // _CHARS_PER_TOKEN) + _MSG_FRAMING_TOKENS


def _schema_json(schema: Any) -> Any:
    if schema is None:
        return None
    if hasattr(schema, "model_json_schema"):
        try:
            return schema.model_json_schema()
        except Exception:  # noqa: BLE001
            return str(schema)
    if isinstance(schema, type):
        return getattr(schema, "__name__", str(schema))
    return schema


def estimate_payload_tokens(
    messages: Sequence[Any] | None,
    *,
    tools: Any = None,
    response_schema: Any = None,
    extra: Any = None,
) -> int:
    """Upper-bound input tokens for a full provider request payload."""
    n = estimate_messages_tokens(messages)
    if tools is not None:
        n += estimate_text_tokens(_jsonish(tools))
    if response_schema is not None:
        n += estimate_text_tokens(_jsonish(_schema_json(response_schema)))
    if extra is not None:
        n += estimate_text_tokens(_jsonish(extra))
    return n


def estimate_invoke_ceiling_usd(
    messages: Sequence[Any] | None,
    *,
    model: str | None = None,
    max_output_tokens: int | None = None,
    tools: Any = None,
    response_schema: Any = None,
    extra: Any = None,
) -> float:
    max_out = (
        cost.DEFAULT_MAX_OUTPUT_TOKENS
        if max_output_tokens is None
        else max(0, int(max_output_tokens))
    )
    return cost.estimate_model_call_ceiling(
        model or cost.active_model() or "gpt-5.4-mini",
        input_tokens=estimate_payload_tokens(
            messages, tools=tools, response_schema=response_schema, extra=extra,
        ),
        max_output_tokens=max_out,
    )


def _usage_usd(msg: Any, model_id: str) -> float:
    usage = getattr(msg, "usage_metadata", None)
    if usage is None:
        return 0.0
    if not isinstance(usage, dict):
        # LangChain UsageMetadata / pydantic model
        try:
            usage = dict(usage)
        except Exception:  # noqa: BLE001
            usage = {
                "input_tokens": getattr(usage, "input_tokens", 0) or 0,
                "output_tokens": getattr(usage, "output_tokens", 0) or 0,
            }
    return cost.estimate_usage_cost(model_id or cost.active_model(), usage)


def _as_messages(value: Any) -> list[BaseMessage]:
    if isinstance(value, list):
        return list(value)
    if isinstance(value, BaseMessage):
        return [value]
    if isinstance(value, dict) and "messages" in value:
        return list(value["messages"] or [])
    return [AIMessage(content=str(value))]


def _message_text(msg: Any) -> str:
    content = getattr(msg, "content", msg)
    if isinstance(content, list):
        parts: list[str] = []
        for part in content:
            if isinstance(part, dict):
                parts.append(str(part.get("text", part)))
            else:
                parts.append(str(part))
        return "".join(parts)
    return content if isinstance(content, str) else _jsonish(content)


def _parse_structured(schema: Any, text: str) -> Any:
    if schema is None:
        return json.loads(text) if text else None
    if hasattr(schema, "model_validate_json"):
        try:
            return schema.model_validate_json(text)
        except Exception:  # noqa: BLE001
            return schema.model_validate(json.loads(text))
    if hasattr(schema, "parse_raw"):
        return schema.parse_raw(text)
    return json.loads(text)


def _settle_amount(out: Any, model_id: str) -> float:
    if isinstance(out, dict) and "raw" in out:
        return _usage_usd(out.get("raw"), model_id)
    if isinstance(out, AIMessage):
        return _usage_usd(out, model_id)
    # Last resort when no raw message is available.
    tokens = estimate_text_tokens(_jsonish(out))
    return cost.estimate_usage_cost(
        model_id or cost.active_model(),
        {"input_tokens": 0, "output_tokens": max(tokens, 1)},
    )


def _caller_structured_shape(out: Any, *, include_raw: bool) -> Any:
    """Map an include_raw provider result back to the caller's requested shape."""
    if include_raw:
        return out
    if isinstance(out, dict) and "parsed" in out:
        return out["parsed"]
    return out


def _split_kwargs(kwargs: dict[str, Any]) -> tuple[Any, Any, dict[str, Any]]:
    tools = kwargs.get("tools") or kwargs.get("functions")
    schema = kwargs.get("response_format") or kwargs.get("schema")
    return tools, schema, kwargs


def _refuse(ceiling: float) -> BudgetRefusedError:
    return BudgetRefusedError(
        f"model call refused ({cost.mode()}): ceiling=${ceiling:.4f} "
        f"remaining=${cost.remaining_usd():.4f}"
    )


def _model_turn_is_essential(gate: BudgetGatedChatModel) -> bool:
    """Finish-path flag for this model turn — never inherited by tool code."""
    return bool(gate.essential) or bool(_turn_essential.get())


def _run_authorized(
    gate: BudgetGatedChatModel,
    messages: list[BaseMessage],
    run: Any,
    *,
    response_schema: Any = None,
    tools: Any = None,
    settle_from: Any,
) -> Any:
    """Reserve → run → settle. No-op authorize when no article budget is active.

    On unknown provider failures, settle the reserved ceiling (conservative): the
    request may have reached the network before raising. BudgetRefusedError is
    local and never billed.

    Essential is taken from the gated model (or a turn-only override), passed
    explicitly to ``try_reserve`` — never via ``cost.essential_scope``, so tool
    executions nested under a draft stream stay non-essential.
    """
    if not cost.is_active():
        return run()
    ceiling = gate._ceiling(messages, response_format=response_schema, tools=tools)
    res = cost.try_reserve(
        ceiling, op="model_turn", essential=_model_turn_is_essential(gate),
    )
    if res is None:
        raise _refuse(ceiling)
    try:
        out = run()
        cost.settle(res, float(settle_from(out)))
        return out
    except BudgetRefusedError:
        cost.release(res)
        raise
    except Exception:
        cost.settle(res, float(res.estimate))
        raise


def _try_inner_structured(inner: Any, schema: Any, kwargs: dict[str, Any]) -> Runnable | None:
    if not hasattr(inner, "with_structured_output"):
        return None
    try:
        return inner.with_structured_output(schema, **kwargs)
    except NotImplementedError:
        return None


def _gated_provider_runnable(
    gate: BudgetGatedChatModel,
    inner_structured: Runnable,
    schema: Any,
    *,
    include_raw: bool,
) -> Runnable:
    from langchain_core.runnables import RunnableLambda

    def _invoke(input_value: Any, config: Any = None) -> Any:
        messages = _as_messages(input_value)
        out = _run_authorized(
            gate,
            messages,
            lambda: inner_structured.invoke(input_value, config=config),
            response_schema=schema,
            settle_from=lambda result: _settle_amount(result, gate.model_id),
        )
        return _caller_structured_shape(out, include_raw=include_raw)

    return RunnableLambda(_invoke)


def _gated_parse_runnable(
    gate: BudgetGatedChatModel,
    schema: Any,
    *,
    include_raw: bool,
) -> Runnable:
    from langchain_core.runnables import RunnableLambda

    def _invoke(input_value: Any, config: Any = None) -> Any:
        messages = _as_messages(input_value)

        def _call() -> AIMessage:
            result = gate._call_inner_generate(messages, None, None)
            msg = result.generations[0].message
            return msg if isinstance(msg, AIMessage) else AIMessage(content=str(msg))

        message = _run_authorized(
            gate,
            messages,
            _call,
            response_schema=schema,
            settle_from=lambda msg: _usage_usd(msg, gate.model_id),
        )
        parsed = _parse_structured(schema, _message_text(message))
        if include_raw:
            return {"raw": message, "parsed": parsed}
        return parsed

    return RunnableLambda(_invoke)


def _scrub_result(result: ChatResult) -> ChatResult:
    """Repair provider-mangled control characters the moment a response arrives.

    The corruption is provider-side, so it can enter through ANY model call, and patching
    each place it was last seen leaking is a losing game: the portfolio and the published
    body were both fixed at their own parse sites, and the next run put NULs into figure
    captions instead, which the published article then inlined ("above 300 " where "€300"
    belonged). Same fault, third surface.

    Everything downstream — contracts, artifacts, slugs, prose — is reached through here, so
    this is the boundary where scrubbing is both complete and done once.
    """
    for gen in result.generations:
        msg = getattr(gen, "message", None)
        if msg is None:
            continue
        if isinstance(msg.content, (str, list)):
            msg.content = scrub(msg.content)
        # Tool-call arguments are model text too, and they become search queries, URLs and
        # written artifacts without ever passing through a message body.
        for call in getattr(msg, "tool_calls", None) or []:
            if isinstance(call, dict) and isinstance(call.get("args"), dict):
                call["args"] = scrub(call["args"])
    return result


class BudgetGatedChatModel(BaseChatModel):
    """``BaseChatModel`` wrapper: reserve → inner generate → settle on every call."""

    model_config = ConfigDict(arbitrary_types_allowed=True)

    inner: Any = Field(exclude=True)
    model_id: str = ""
    max_output_tokens: int = cost.DEFAULT_MAX_OUTPUT_TOKENS
    essential: bool = False
    #: Who is actually on the other end, and where. Carried for DIAGNOSIS as much as for
    #: reconnection: the client library is OpenAI-shaped for several providers, so a raw
    #: ``openai.APIConnectionError`` names the protocol rather than the vendor and reads as
    #: "OpenAI is down" when the call went to Meta. Errors are re-labelled with these.
    provider: str = ""
    base_url: str = ""

    @property
    def _llm_type(self) -> str:
        return "budget_gated"

    @property
    def _identifying_params(self) -> dict[str, Any]:
        return {"model_id": self.model_id, "inner": type(self.inner).__name__}

    def _ceiling(self, messages: list[BaseMessage], **kwargs: Any) -> float:
        tools, schema, _ = _split_kwargs(kwargs)
        return estimate_invoke_ceiling_usd(
            messages,
            model=self.model_id or cost.active_model(),
            max_output_tokens=self.max_output_tokens,
            tools=tools,
            response_schema=schema,
        )

    def _call_inner_generate(
        self,
        messages: list[BaseMessage],
        stop: list[str] | None,
        run_manager: CallbackManagerForLLMRun | None,
        **kwargs: Any,
    ) -> ChatResult:
        def _call() -> ChatResult:
            if isinstance(self.inner, BaseChatModel):
                return self.inner._generate(  # noqa: SLF001 — intentional inner delegation
                    messages, stop=stop, run_manager=run_manager, **kwargs,
                )
            msg = self.inner.invoke(messages, stop=stop, **kwargs)
            if not isinstance(msg, AIMessage):
                msg = AIMessage(content=str(msg))
            return ChatResult(generations=[ChatGeneration(message=msg)])

        # THE single place every model call reaches a provider, so it is where a dropped
        # connection is worth surviving. A rail died mid-gauntlet on one APIConnectionError
        # after the pool, synthesis and a full profile had already been paid for; the outage
        # lasted seconds and the pipeline has no resume, so recovery meant re-buying all of
        # it. Holding the call here loses nothing, because nothing upstream unwinds.
        from .reconnect import call_with_reconnect

        result = call_with_reconnect(
            _call,
            probe_url=self.base_url,
            on_wait=lambda m: print(f"[model:{self.provider or '?'}] {m}", flush=True),
        )
        return _scrub_result(result)

    def _generate(
        self,
        messages: list[BaseMessage],
        stop: list[str] | None = None,
        run_manager: CallbackManagerForLLMRun | None = None,
        **kwargs: Any,
    ) -> ChatResult:
        return _run_authorized(
            self,
            messages,
            lambda: self._call_inner_generate(messages, stop, run_manager, **kwargs),
            response_schema=kwargs.get("response_format") or kwargs.get("schema"),
            tools=kwargs.get("tools") or kwargs.get("functions"),
            settle_from=lambda result: _usage_usd(
                result.generations[0].message, self.model_id,
            ),
        )

    def _stream(
        self,
        messages: list[BaseMessage],
        stop: list[str] | None = None,
        run_manager: CallbackManagerForLLMRun | None = None,
        **kwargs: Any,
    ) -> Iterator[ChatGenerationChunk]:
        # Prefer one-shot generate for metering certainty; stream only when inactive.
        if not cost.is_active():
            if hasattr(self.inner, "_stream"):
                # The one path that skips _call_inner_generate, so it scrubs its own chunks.
                for chunk in self.inner._stream(  # noqa: SLF001
                    messages, stop=stop, run_manager=run_manager, **kwargs,
                ):
                    if isinstance(chunk.message.content, (str, list)):
                        chunk.message.content = scrub(chunk.message.content)
                    yield chunk
                return
            result = self._call_inner_generate(messages, stop, run_manager, **kwargs)
            yield ChatGenerationChunk(message=result.generations[0].message)
            return

        result = self._generate(messages, stop=stop, run_manager=run_manager, **kwargs)
        yield ChatGenerationChunk(message=result.generations[0].message)

    def bind_tools(
        self,
        tools: Sequence[Any],
        *,
        tool_choice: str | None = None,
        **kwargs: Any,
    ) -> Runnable:
        """Bind tools on the inner provider, then re-bind onto this gate.

        LangGraph ``create_react_agent`` calls ``bind_tools`` during construction.
        Binding on ``inner`` alone would return an ungated ``RunnableBinding``;
        re-binding the formatted kwargs onto ``self`` keeps every turn authorized.
        """
        from langchain_core.runnables import RunnableBinding

        try:
            bound = self.inner.bind_tools(tools, tool_choice=tool_choice, **kwargs)
        except NotImplementedError:
            bind_kwargs: dict[str, Any] = {"tools": list(tools), **kwargs}
            if tool_choice is not None:
                bind_kwargs["tool_choice"] = tool_choice
            return self.bind(**bind_kwargs)

        if isinstance(bound, RunnableBinding):
            return self.bind(**bound.kwargs)
        # Unusual provider return — keep the gate as the invoke surface when possible.
        if isinstance(bound, BaseChatModel):
            return gate_chat_model(
                bound,
                model_id=self.model_id,
                max_output_tokens=self.max_output_tokens,
                essential=self.essential,
            )
        return bound

    def with_structured_output(self, schema: Any = None, **kwargs: Any) -> Runnable:
        """Authorize structured calls the same way as plain chat turns.

        Prefer the provider's structured path when available (correct
        ``response_format`` / tool-calling), but reserve *before* that invoke so
        LangGraph's ``generate_structured_response`` cannot bypass the hard cap.
        Always request ``include_raw=True`` internally so settle sees usage on the
        raw ``AIMessage``, then return the caller's requested shape.
        """
        want_raw = bool(kwargs.get("include_raw", False))
        provider_kwargs = {**kwargs, "include_raw": True}
        inner_structured = _try_inner_structured(self.inner, schema, provider_kwargs)
        if inner_structured is not None:
            return _gated_provider_runnable(
                self, inner_structured, schema, include_raw=want_raw,
            )
        return _gated_parse_runnable(self, schema, include_raw=want_raw)


def gate_chat_model(
    model: Any,
    *,
    model_id: str = "",
    max_output_tokens: int | None = None,
    essential: bool | None = None,
    provider: str = "",
    base_url: str = "",
) -> Any:
    """Wrap a chat model so every generation is budget-authorized. Idempotent."""
    max_out = (
        cost.DEFAULT_MAX_OUTPUT_TOKENS
        if max_output_tokens is None
        else max(0, int(max_output_tokens))
    )
    if isinstance(model, BudgetGatedChatModel):
        updates: dict[str, Any] = {"max_output_tokens": max_out}
        if essential is not None:
            updates["essential"] = bool(essential)
        return model.model_copy(update=updates)
    if isinstance(model, BaseChatModel):
        mid = (
            model_id
            or getattr(model, "model_name", None)
            or getattr(model, "model", None)
            or ""
        )
        return BudgetGatedChatModel(
            inner=model,
            model_id=str(mid),
            max_output_tokens=max_out,
            essential=bool(essential) if essential is not None else False,
            provider=provider,
            base_url=base_url or str(getattr(model, "openai_api_base", "") or ""),
        )
    return model
