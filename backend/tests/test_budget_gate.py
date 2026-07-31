"""Budget gate at the chat-model invocation boundary."""

from __future__ import annotations

from typing import Any

import pytest
from langchain_core.language_models.chat_models import BaseChatModel
from langchain_core.messages import AIMessage, HumanMessage, SystemMessage
from langchain_core.outputs import ChatGeneration, ChatResult
from langchain_core.runnables import RunnableBinding, RunnableLambda
from langchain_core.tools import tool
from pydantic import BaseModel, Field

from algent_backend.agent_system.agents.loop import build_react_loop
from algent_backend.agent_system.foundation import cost
from algent_backend.agent_system.foundation.models.budget_gate import (
    BudgetGatedChatModel,
    BudgetRefusedError,
    estimate_invoke_ceiling_usd,
    estimate_payload_tokens,
    gate_chat_model,
)


class _Out(BaseModel):
    title: str = Field(description="a title")


class _FakeChat(BaseChatModel):
    """Records calls; returns a fixed AIMessage with optional usage."""

    calls: list[Any] = Field(default_factory=list)
    usage: dict[str, Any] = Field(
        default_factory=lambda: {
            "input_tokens": 10,
            "output_tokens": 5,
            "total_tokens": 15,
        },
    )
    boom: bool = False

    @property
    def _llm_type(self) -> str:
        return "fake"

    def _generate(self, messages, stop=None, run_manager=None, **kwargs):
        self.calls.append({"messages": list(messages), "kwargs": dict(kwargs)})
        if self.boom:
            raise RuntimeError("provider failed after network contact")
        msg = AIMessage(content='{"title": "t"}', usage_metadata=dict(self.usage))
        return ChatResult(generations=[ChatGeneration(message=msg)])


class _ProviderStructuredFake(BaseChatModel):
    """Mimics provider WSO: parsed-only by default; raw+parsed when include_raw."""

    usage: dict[str, Any] = Field(
        default_factory=lambda: {
            "input_tokens": 1000,
            "output_tokens": 5,
            "total_tokens": 1005,
        },
    )

    @property
    def _llm_type(self) -> str:
        return "provider_structured_fake"

    def _generate(self, messages, stop=None, run_manager=None, **kwargs):
        msg = AIMessage(content='{"title": "t"}', usage_metadata=dict(self.usage))
        return ChatResult(generations=[ChatGeneration(message=msg)])

    def with_structured_output(self, schema: Any = None, **kwargs: Any):
        include_raw = bool(kwargs.get("include_raw", False))
        usage = dict(self.usage)

        def _invoke(input_value: Any, config: Any = None) -> Any:
            raw = AIMessage(content='{"title": "t"}', usage_metadata=usage)
            parsed = schema.model_validate_json(raw.content) if schema else {"title": "t"}
            if include_raw:
                return {"raw": raw, "parsed": parsed}
            return parsed

        return RunnableLambda(_invoke)


@tool
def _ping(query: str) -> str:
    """Echo a query string (dummy tool for ReAct construction)."""
    return query


def test_payload_tokens_include_system_tools_and_schema() -> None:
    messages = [HumanMessage(content="hi")]
    bare = estimate_payload_tokens(messages)
    with_sys = estimate_payload_tokens(
        [SystemMessage(content="S" * 300), HumanMessage(content="hi")],
    )
    with_tools = estimate_payload_tokens(
        messages, tools=[{"name": "web_search", "description": "d" * 300}],
    )
    with_schema = estimate_payload_tokens(messages, response_schema=_Out)
    assert with_sys > bare
    assert with_tools > bare
    assert with_schema > bare
    # Combined ceiling exceeds message-only ceiling.
    full = estimate_invoke_ceiling_usd(
        [SystemMessage(content="S" * 300), HumanMessage(content="hi")],
        model="gpt-5.4-mini",
        tools=[{"name": "web_search", "description": "d" * 300}],
        response_schema=_Out,
    )
    msgs_only = estimate_invoke_ceiling_usd(
        [SystemMessage(content="S" * 300), HumanMessage(content="hi")],
        model="gpt-5.4-mini",
    )
    assert full > msgs_only


def test_structured_response_path_is_reserved_and_settled() -> None:
    fake = _FakeChat()
    gated = gate_chat_model(fake, model_id="gpt-5.4-mini")
    assert isinstance(gated, BudgetGatedChatModel)

    with cost.article_scoped(3.0, soft_usd=3.0):
        structured = gated.with_structured_output(_Out)
        out = structured.invoke([HumanMessage(content="write a title")])
        assert fake.calls, "inner model must be invoked"
        assert cost.article_spent_usd() > 0
        assert cost.snapshot()["reserved_usd"] == 0.0
        title = getattr(out, "title", None) or (
            out.get("title") if isinstance(out, dict) else None
        )
        assert title == "t"


def test_structured_settles_from_raw_usage_metadata() -> None:
    """Provider parsed-only returns must not drop input-token cost."""
    fake = _ProviderStructuredFake()
    gated = gate_chat_model(fake, model_id="gpt-5.4-mini")
    expected = cost.estimate_usage_cost("gpt-5.4-mini", dict(fake.usage))

    with cost.article_scoped(3.0, soft_usd=3.0):
        out = gated.with_structured_output(_Out).invoke(
            [HumanMessage(content="write a title")],
        )
        assert out.title == "t"
        assert cost.article_spent_usd() == pytest.approx(expected, abs=1e-5)
        # Output-size-only settle would be far cheaper than 1000 input tokens.
        output_only = cost.estimate_usage_cost(
            "gpt-5.4-mini", {"input_tokens": 0, "output_tokens": 5},
        )
        assert cost.article_spent_usd() > output_only * 10


def test_structured_reservation_includes_schema_overhead() -> None:
    """Schema tokens must raise the pre-call ceiling vs messages alone."""
    messages = [HumanMessage(content="hi")]
    bare = estimate_invoke_ceiling_usd(messages, model="gpt-5.4-mini")
    with_schema = estimate_invoke_ceiling_usd(
        messages, model="gpt-5.4-mini", response_schema=_Out,
    )
    assert with_schema > bare

    fake = _FakeChat()
    gated = gate_chat_model(fake, model_id="gpt-5.4-mini")
    # Cap just below the schema-inclusive ceiling but above message-only.
    mid = (bare + with_schema) / 2
    with cost.article_scoped(mid, soft_usd=mid):
        with pytest.raises(BudgetRefusedError):
            gated.with_structured_output(_Out).invoke(messages)
    assert fake.calls == []


def test_model_request_does_not_begin_when_reservation_exceeds_hard_cap() -> None:
    fake = _FakeChat()
    gated = gate_chat_model(fake, model_id="gpt-5.4-mini")
    huge = [HumanMessage(content="x" * 200_000)]  # large input → high ceiling

    with cost.article_scoped(0.01, soft_usd=0.01):  # tiny hard cap
        with pytest.raises(BudgetRefusedError):
            gated.invoke(huge)
    assert fake.calls == []  # provider never contacted


def test_provider_failure_settles_reservation_estimate() -> None:
    fake = _FakeChat(boom=True)
    gated = gate_chat_model(fake, model_id="gpt-5.4-mini")
    messages = [HumanMessage(content="hi")]
    ceiling = estimate_invoke_ceiling_usd(messages, model="gpt-5.4-mini")

    with cost.article_scoped(3.0, soft_usd=3.0):
        with pytest.raises(RuntimeError, match="provider failed"):
            gated.invoke(messages)
        assert cost.snapshot()["reserved_usd"] == 0.0
        assert cost.article_spent_usd() == pytest.approx(ceiling, abs=1e-5)


def test_build_react_loop_accepts_gated_model_with_tools() -> None:
    """LangGraph construction calls bind_tools — must not raise NotImplementedError."""
    fake = _FakeChat()
    agent = build_react_loop(fake, [_ping], system_prompt="You are a test agent.")
    assert agent is not None

    gated = gate_chat_model(fake, model_id="gpt-5.4-mini")
    bound = gated.bind_tools([_ping])
    assert isinstance(bound, RunnableBinding)
    assert isinstance(bound.bound, BudgetGatedChatModel)
    assert "tools" in bound.kwargs


def test_essential_draft_model_proceeds_in_slim_keyword_tool_refused() -> None:
    """Finish-path model turns stay authorized under slim; primary search does not.

    Regression for wrapping the whole ReAct stream in ``cost.essential_scope``,
    which made draft-time keyword reserves inherit essential=True.
    """
    from algent_backend.agent_system.foundation.models.budget_gate import (
        turn_essential_scope,
    )
    from algent_backend.agent_system.tools.sourcing.search import research

    fake = _FakeChat()
    essential_model = gate_chat_model(fake, model_id="gpt-5.4-mini", essential=True)
    plain = gate_chat_model(_FakeChat(), model_id="gpt-5.4-mini", essential=False)

    with cost.article_scoped(3.0, soft_usd=1.0):
        cost.add(1.0)
        assert cost.mode() == "slim_finish"

        # Essential gated model (draft finish path) may still reserve.
        essential_model.invoke([HumanMessage(content="finish the draft")])
        assert fake.calls

        # Plain model turns refuse under slim.
        with pytest.raises(BudgetRefusedError):
            plain.invoke([HumanMessage(content="optional turn")])

        # Stream-style turn essential must NOT authorize tool reserves.
        with turn_essential_scope(True):
            assert cost.try_reserve(0.008, op="keyword") is None
            out = research._search_web("soft-cap leak?", "keyword", 3)  # noqa: SLF001
            assert "error" in out
            assert "refused" in out["error"] or "slim" in out["error"]


def test_gate_is_idempotent() -> None:
    fake = _FakeChat()
    once = gate_chat_model(fake, model_id="gpt-5.4-mini")
    twice = gate_chat_model(once, model_id="gpt-5.4-mini")
    assert once is twice or isinstance(twice, BudgetGatedChatModel)
    assert twice.inner is fake or twice.inner is once.inner
