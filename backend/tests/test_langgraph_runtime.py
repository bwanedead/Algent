"""
Smoke tests for the LangGraph runtime rail (Slice 1).

Proves a neutral ``RunRequest`` executes ``hello_workflow`` through
``RuntimeRegistry`` -> ``LangGraphAdapter`` without live API calls.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

import pytest

from algent_backend.agent_system.agents.hello_workflow import AGENT_ID
from algent_backend.agent_system.foundation.models import ModelResolver, ModelSpec, ResolvedModel
from algent_backend.agent_system.runs import AgentRunContext, RunRequest
from algent_backend.agent_system.runtime import RuntimeRegistry


@dataclass
class FakeChatModel:
    """Minimal LangChain-like chat model for offline tests."""

    response: str = "A concise brief about the topic."
    invoked: bool = field(default=False, init=False)
    last_messages: list[Any] = field(default_factory=list, init=False)

    def invoke(self, messages: list[Any]) -> str:
        self.invoked = True
        self.last_messages = list(messages)
        return self.response


class FakeModelResolver(ModelResolver):
    """Returns a predetermined fake client instead of building a real model."""

    def __init__(self, client: FakeChatModel) -> None:
        super().__init__(targets=[])
        self._client = client

    def resolve(self, spec: ModelSpec, target: str = "langchain") -> ResolvedModel:
        return ResolvedModel(
            provider=spec.provider,
            target=target,
            model=spec.model,
            client=self._client,
        )


def test_hello_workflow_completes_through_runtime_registry() -> None:
    fake_model = FakeChatModel(response="Brief: quantum computing basics.")
    context = AgentRunContext(run_id="run-123", model_resolver=FakeModelResolver(fake_model))
    request = RunRequest(agent_id=AGENT_ID, input={"topic": "quantum computing"})

    result = RuntimeRegistry().run(request, context)

    assert result.status == "completed"
    assert result.run_id == "run-123"
    assert result.agent_id == AGENT_ID
    assert result.runtime == "langgraph"
    assert result.error is None
    assert result.output["topic"] == "quantum computing"
    assert result.output["brief"] == "Brief: quantum computing basics."
    assert fake_model.invoked is True
    assert len(fake_model.last_messages) == 1


def test_unknown_agent_returns_failed_result() -> None:
    fake_model = FakeChatModel()
    context = AgentRunContext(run_id="run-404", model_resolver=FakeModelResolver(fake_model))
    request = RunRequest(agent_id="missing_agent", input={"topic": "nothing"})

    result = RuntimeRegistry().run(request, context)

    assert result.status == "failed"
    assert result.agent_id == "missing_agent"
    assert "Unknown agent" in (result.error or "")
    assert fake_model.invoked is False


def test_unknown_runtime_raises() -> None:
    fake_model = FakeChatModel()
    context = AgentRunContext(run_id="run-500", model_resolver=FakeModelResolver(fake_model))
    request = RunRequest(agent_id=AGENT_ID, input={"topic": "test"}, runtime="native")

    with pytest.raises(ValueError, match="Unknown runtime"):
        RuntimeRegistry().run(request, context)
