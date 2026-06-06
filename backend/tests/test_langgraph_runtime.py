"""
Smoke tests for orchestration: AgentRegistry, RunService, and the adapter.

Proves agents are first-class (registered, looked up), that ``RunService`` owns
context creation, and that the adapter executes whatever ``AgentSpec`` it is
handed. No live API calls.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from algent_backend.agent_system.agents import default_agent_registry
from algent_backend.agent_system.agents.agent_spec import AgentSpec
from algent_backend.agent_system.foundation.models import ModelResolver, ModelSpec, ResolvedModel
from algent_backend.agent_system.runs import AgentRunContext, RunRequest
from algent_backend.agent_system.runs.service import RunService
from algent_backend.agent_system.runtime.langgraph import LangGraphAdapter
from algent_backend.agent_system.tools import GLOBAL_SCOPE, ToolRegistry, ToolSpec


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


class FakeCompiled:
    """Stand-in for a compiled graph: echoes the input plus a marker."""

    def invoke(self, payload: dict[str, Any]) -> dict[str, Any]:
        return {**payload, "ran": True}


def _context(run_id: str = "run-1", response: str = "Brief.") -> AgentRunContext:
    return AgentRunContext(run_id=run_id, model_resolver=FakeModelResolver(FakeChatModel(response)))


def _service(response: str = "Brief.", tool_registry: ToolRegistry | None = None) -> RunService:
    return RunService(
        model_resolver=FakeModelResolver(FakeChatModel(response)),
        tool_registry=tool_registry if tool_registry is not None else ToolRegistry(),
    )


def test_agent_registry_returns_known_specs() -> None:
    registry = default_agent_registry()
    assert registry.get("hello_workflow").runtime == "langgraph"
    assert registry.get("news_brief").family == "news"
    ids = {s.agent_id for s in registry.list()}
    assert {"hello_workflow", "news_brief"} <= ids


def test_run_service_creates_context_and_runs_hello_workflow() -> None:
    request = RunRequest(agent_id="hello_workflow", input={"topic": "quantum computing"})

    result = _service(response="Brief: quantum computing basics.").run(request)

    assert result.status == "completed"
    assert result.run_id  # RunService generates a uuid
    assert result.agent_id == "hello_workflow"
    assert result.runtime == "langgraph"
    assert result.error is None
    assert result.output["topic"] == "quantum computing"
    assert result.output["brief"] == "Brief: quantum computing basics."


def test_adapter_executes_any_spec_it_is_handed() -> None:
    """The adapter knows no catalog — it runs whatever AgentSpec it receives."""
    import algent_backend.agent_system.runtime.langgraph as langgraph_module

    assert not hasattr(langgraph_module, "_AGENT_BUILDERS")

    spec = AgentSpec(
        agent_id="echo",
        name="Echo",
        runtime="langgraph",
        build_graph=lambda _context: FakeCompiled(),
    )
    request = RunRequest(agent_id="echo", input={"topic": "hi"})

    result = LangGraphAdapter().run(request, _context(), spec)

    assert result.status == "completed"
    assert result.agent_id == "echo"
    assert result.output == {"topic": "hi", "ran": True}


def test_unknown_agent_returns_failed_result() -> None:
    request = RunRequest(agent_id="missing_agent", input={"topic": "nothing"})

    result = _service().run(request)

    assert result.status == "failed"
    assert result.agent_id == "missing_agent"
    assert "Unknown agent" in (result.error or "")


def test_runtime_mismatch_returns_failed_result() -> None:
    spec = AgentSpec(
        agent_id="native_agent",
        name="Native Agent",
        runtime="native",
        build_graph=lambda _context: FakeCompiled(),
    )
    request = RunRequest(agent_id="native_agent", input={})

    result = LangGraphAdapter().run(request, _context(), spec)

    assert result.status == "failed"
    assert "runtime" in (result.error or "").lower()


def test_unknown_runtime_handled_by_run_service() -> None:
    request = RunRequest(agent_id="hello_workflow", input={"topic": "x"}, runtime="native")

    result = _service().run(request)

    assert result.status == "failed"
    assert "Unknown runtime" in (result.error or "")


def test_no_tool_agent_does_not_build_global_tools() -> None:
    """A global tool resolves for hello_workflow but must not be built (it's unused)."""

    def _explode() -> object:
        raise RuntimeError("missing TAVILY_API_KEY")

    registry = ToolRegistry()
    registry.register(
        ToolSpec(
            tool_id="web_search",
            name="Web Search",
            description="",
            scope=GLOBAL_SCOPE,
            build=_explode,
        )
    )
    request = RunRequest(agent_id="hello_workflow", input={"topic": "x"})

    result = _service(tool_registry=registry).run(request)

    assert result.status == "completed"  # hello never accesses tools, so _explode never runs


def test_run_service_fails_on_unknown_required_tool() -> None:
    # news_brief requires web_search; an empty tool registry makes that unresolvable.
    request = RunRequest(agent_id="news_brief", input={"topic": "x"})

    result = _service(tool_registry=ToolRegistry()).run(request)

    assert result.status == "failed"
    assert "Unknown required tool" in (result.error or "")
