"""
A gateway 504 on a big structured call must not kill a rail run.

Two rail runs and a geopolitics daily died on ``openai.InternalServerError`` 504 "Request exceeded
the non-streaming server time limit" inside LangGraph's ``generate_structured_response``. Two gaps:
the structured path called the provider client directly, so ``reconnect`` never wrapped it; and
every house spec's ``streaming=True`` was silently forced off, so nothing streamed. These tests pin
the repair with fakes (and a mocked HTTP transport for the real ``ChatOpenAI`` stream parsing).
"""

from __future__ import annotations

import json
from typing import Any

import httpx
import pytest
from langchain_core.language_models.chat_models import BaseChatModel
from langchain_core.messages import AIMessage, HumanMessage
from langchain_core.outputs import ChatGeneration, ChatResult
from langchain_core.runnables import RunnableLambda
from pydantic import BaseModel, Field

from algent_backend.agent_system.foundation import cost
from algent_backend.agent_system.foundation.models import provider_errors, reconnect
from algent_backend.agent_system.foundation.models.budget_gate import gate_chat_model

STREAM_REQUIRED = (
    'Error code: 504 - Request exceeded the non-streaming server time limit before a response was '
    'produced. For large or slow requests, use the streaming API by setting "stream": true.'
)
USAGE = {"input_tokens": 1000, "output_tokens": 50, "total_tokens": 1050}


class _Out(BaseModel):
    title: str


class _InternalServerError(Exception):
    """Stands in for openai.InternalServerError (matched by NAME, like reconnect does)."""

    status_code = 504


_InternalServerError.__name__ = "InternalServerError"


class _Fake(BaseChatModel):
    """A provider client whose structured calls fail ``fail_with`` times, then succeed."""

    fail_with: list[Exception] = Field(default_factory=list)
    calls: list[str] = Field(default_factory=list)
    label: str = "plain"

    @property
    def _llm_type(self) -> str:
        return "fake"

    def _generate(self, messages, stop=None, run_manager=None, **kwargs):
        self.calls.append(self.label)
        if self.fail_with:
            raise self.fail_with.pop(0)
        msg = AIMessage(content='{"title": "t"}', usage_metadata=dict(USAGE))
        return ChatResult(generations=[ChatGeneration(message=msg)])

    def with_structured_output(self, schema: Any = None, **kwargs: Any):
        def _invoke(_input: Any, config: Any = None) -> Any:
            self.calls.append(self.label)
            if self.fail_with:
                raise self.fail_with.pop(0)
            raw = AIMessage(content='{"title": "t"}', usage_metadata=dict(USAGE))
            return {"raw": raw, "parsed": _Out(title="t")}

        return RunnableLambda(_invoke)


@pytest.fixture(autouse=True)
def _no_waiting(monkeypatch) -> None:
    monkeypatch.setattr(reconnect.time, "sleep", lambda _s: None)
    monkeypatch.setattr(reconnect, "probe", lambda url, timeout=5.0: True)


def _spent_for_one_call() -> float:
    return cost.estimate_usage_cost("gpt-5.4-mini", dict(USAGE))


def test_a_transient_504_on_the_structured_path_is_retried_and_billed_once() -> None:
    plain = _Fake(fail_with=[_InternalServerError("gateway timeout")])
    gated = gate_chat_model(plain, model_id="gpt-5.4-mini")
    with cost.article_scoped(3.0, soft_usd=3.0):
        out = gated.with_structured_output(_Out).invoke([HumanMessage(content="structure it")])
        assert out.title == "t"
        assert plain.calls == ["plain", "plain"]                       # failed once, retried, done
        # One logical call: one reservation, settled once from the call that succeeded. The failed
        # attempt neither double-charges nor leaves a reservation held.
        assert cost.article_spent_usd() == pytest.approx(_spent_for_one_call(), abs=1e-6)
        assert cost.snapshot()["reserved_usd"] == 0.0


def test_a_non_transient_error_still_raises_immediately() -> None:
    plain = _Fake(fail_with=[ValueError("schema rejected"), ValueError("again")])
    gated = gate_chat_model(plain, model_id="gpt-5.4-mini")
    with pytest.raises(ValueError, match="schema rejected"):
        gated.with_structured_output(_Out).invoke([HumanMessage(content="x")])
    assert plain.calls == ["plain"]


def test_stream_required_is_classified_and_never_waited_on() -> None:
    exc = _InternalServerError(STREAM_REQUIRED)
    assert provider_errors.is_stream_required(exc) is True
    wrapped = RuntimeError("task failed")
    wrapped.__cause__ = exc
    assert provider_errors.is_stream_required(wrapped) is True
    assert reconnect.is_connection_error(exc) is False                 # same 504, but waiting is futile
    assert reconnect.is_connection_error(_InternalServerError("gateway timeout")) is True
    assert provider_errors.is_stream_required(ValueError("nope")) is False


def test_a_stream_required_504_escalates_to_a_stream_instead_of_retrying() -> None:
    plain = _Fake(fail_with=[_InternalServerError(STREAM_REQUIRED)] * 10)
    twin = _Fake(label="stream")
    gated = gate_chat_model(plain, model_id="gpt-5.4-mini", stream_inner=twin)
    with cost.article_scoped(3.0, soft_usd=3.0):
        out = gated.with_structured_output(_Out).invoke([HumanMessage(content="structure it")])
        assert out.title == "t"
        assert plain.calls == ["plain"]                                # one try, no 15-minute retry loop
        assert twin.calls == ["stream"]
        assert cost.article_spent_usd() == pytest.approx(_spent_for_one_call(), abs=1e-6)
        assert cost.snapshot()["reserved_usd"] == 0.0


def test_a_stream_required_504_without_a_streaming_twin_raises_at_once() -> None:
    plain = _Fake(fail_with=[_InternalServerError(STREAM_REQUIRED)] * 10)
    gated = gate_chat_model(plain, model_id="gpt-5.4-mini")
    with pytest.raises(_InternalServerError):
        gated.with_structured_output(_Out).invoke([HumanMessage(content="x")])
    assert plain.calls == ["plain"]


def test_a_spec_that_asked_for_streaming_streams_from_the_first_request() -> None:
    plain, twin = _Fake(), _Fake(label="stream")
    gated = gate_chat_model(plain, model_id="gpt-5.4-mini", stream_inner=twin, stream_structured=True)
    assert gated.with_structured_output(_Out).invoke([HumanMessage(content="x")]).title == "t"
    assert plain.calls == [] and twin.calls == ["stream"]


def test_a_transient_failure_on_the_streamed_request_is_retried_too() -> None:
    plain, twin = _Fake(), _Fake(label="stream", fail_with=[_InternalServerError("bad gateway")])
    gated = gate_chat_model(plain, model_id="gpt-5.4-mini", stream_inner=twin, stream_structured=True)
    assert gated.with_structured_output(_Out).invoke([HumanMessage(content="x")]).title == "t"
    assert twin.calls == ["stream", "stream"]


def test_a_plain_turn_is_retried_and_escalates_the_same_way() -> None:
    plain = _Fake(fail_with=[_InternalServerError("gateway timeout")])
    assert gate_chat_model(plain, model_id="m").invoke("hi").content == '{"title": "t"}'
    assert plain.calls == ["plain", "plain"]

    plain = _Fake(fail_with=[_InternalServerError(STREAM_REQUIRED)])
    gated = gate_chat_model(plain, model_id="m", stream_inner=_StreamTwin())
    assert gated.invoke("hi").content == "streamed"


class _StreamTwin(_Fake):
    label: str = "stream"

    def _stream(self, messages, stop=None, run_manager=None, **kwargs):
        from langchain_core.messages import AIMessageChunk
        from langchain_core.outputs import ChatGenerationChunk

        self.calls.append("stream")
        yield ChatGenerationChunk(message=AIMessageChunk(content="stream"))
        yield ChatGenerationChunk(message=AIMessageChunk(content="ed"))


# ── the real ChatOpenAI, over a mocked wire ───────────────────────────────────────────────────
def _response(status: str, output: list) -> dict:
    return {
        "id": "resp_1", "object": "response", "created_at": 1, "status": status, "model": "m",
        "output": output, "parallel_tool_calls": True, "tool_choice": "auto", "tools": [],
        "text": {"format": {"type": "json_schema", "name": "_Out", "strict": True,
                            "schema": {"type": "object"}}},
        "usage": {"input_tokens": 10, "output_tokens": 5, "total_tokens": 15,
                  "input_tokens_details": {"cached_tokens": 0},
                  "output_tokens_details": {"reasoning_tokens": 0}},
    }


def _sse(events: list) -> str:
    return "".join(
        f"event: {t}\ndata: {json.dumps({'type': t, 'sequence_number': i, **d})}\n\n"
        for i, (t, d) in enumerate(events)
    )


def _wire(requests: list[dict]):
    text = '{"title":"hi"}'
    done = {"id": "msg_1", "type": "message", "role": "assistant", "status": "completed",
            "content": [{"type": "output_text", "text": text, "annotations": []}]}
    live = {**done, "status": "in_progress", "content": []}
    where = {"item_id": "msg_1", "output_index": 0, "content_index": 0}
    events = [
        ("response.created", {"response": _response("in_progress", [])}),
        ("response.output_item.added", {"output_index": 0, "item": live}),
        ("response.content_part.added", {**where, "part": {"type": "output_text", "text": "", "annotations": []}}),
        ("response.output_text.delta", {**where, "delta": text, "logprobs": []}),
        ("response.output_text.done", {**where, "text": text, "logprobs": []}),
        ("response.completed", {"response": _response("completed", [done])}),
    ]

    def handler(request: httpx.Request) -> httpx.Response:
        body = json.loads(request.content)
        requests.append(body)
        if body.get("stream"):
            return httpx.Response(200, headers={"content-type": "text/event-stream"}, content=_sse(events))
        return httpx.Response(504, json={"error": {"code": "gateway_timeout", "type": "server_error",
                                                   "message": STREAM_REQUIRED}})

    return handler


def _real_gate(requests: list[dict], *, stream_structured: bool):
    pytest.importorskip("langchain_openai")
    from langchain_openai import ChatOpenAI

    http = httpx.Client(transport=httpx.MockTransport(_wire(requests)))
    client = ChatOpenAI(model="m", api_key="test", base_url="http://mock/v1", http_client=http,
                        use_responses_api=True, reasoning_effort="medium", streaming=False, max_retries=0)
    twin = client.model_copy(update={"streaming": True, "stream_usage": True})
    return gate_chat_model(client, model_id="gpt-5.4-mini", stream_inner=twin,
                           stream_structured=stream_structured)


def test_real_client_streams_structured_output_and_keeps_usage_for_settling() -> None:
    """Evidence that the installed langchain_openai streams WITH structured output (Responses API):
    the parsed object and the usage the cost ledger settles from both survive the stream."""
    requests: list[dict] = []
    gated = _real_gate(requests, stream_structured=True)
    with cost.article_scoped(3.0, soft_usd=3.0):
        out = gated.with_structured_output(_Out).invoke([HumanMessage(content="x")])
        assert out == _Out(title="hi")
        assert [r.get("stream") for r in requests] == [True]
        assert cost.article_spent_usd() > 0
        assert cost.snapshot()["reserved_usd"] == pytest.approx(0.0, abs=1e-5)   # rounding residue only


def test_real_client_unstreamed_504_escalates_to_a_stream() -> None:
    requests: list[dict] = []
    gated = _real_gate(requests, stream_structured=False)
    out = gated.with_structured_output(_Out).invoke([HumanMessage(content="x")])
    assert out == _Out(title="hi")
    assert [bool(r.get("stream")) for r in requests] == [False, True]


def test_target_keeps_the_react_client_unstreamed_but_hands_the_gate_a_stream_twin(monkeypatch) -> None:
    from algent_backend.agent_system.foundation.models.specs import ModelSpec
    from algent_backend.agent_system.foundation.models.targets.langchain import LangChainTarget

    monkeypatch.setenv("OPENAI_API_KEY", "test")
    spec = ModelSpec(provider="openai", model="gpt-5.4-mini", reasoning_effort="medium",
                     extra={"streaming": True, "stream_usage": True})
    gate = LangChainTarget().resolve(spec).client
    assert gate.inner.streaming is False                  # ReAct turns call _generate directly
    assert gate.stream_inner is not None and gate.stream_inner.streaming is True
    assert "streaming" in gate.stream_inner.model_fields_set
    assert gate.stream_structured is True
    plain_spec = ModelSpec(provider="openai", model="gpt-5.4-mini", reasoning_effort="medium")
    assert LangChainTarget().resolve(plain_spec).client.stream_structured is False
