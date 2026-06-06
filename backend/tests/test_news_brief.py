"""
Offline end-to-end test for the news_brief agent.

Uses a fake web_search tool (deterministic results) and a fake model resolver, so
no live Tavily or model calls happen. Proves the agent searches through the tool
seam and produces a brief via RunService-owned context assembly.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from algent_backend.agent_system.foundation.models import ModelResolver, ModelSpec, ResolvedModel
from algent_backend.agent_system.runs import RunRequest
from algent_backend.agent_system.runs.service import RunService
from algent_backend.agent_system.tools import GLOBAL_SCOPE, ToolRegistry, ToolSpec


@dataclass
class FakeChatModel:
    response: str = "BRIEF: grounded summary."
    invoked: bool = field(default=False, init=False)
    last_messages: list[Any] = field(default_factory=list, init=False)

    def invoke(self, messages: list[Any]) -> str:
        self.invoked = True
        self.last_messages = list(messages)
        return self.response


class FakeModelResolver(ModelResolver):
    def __init__(self, client: FakeChatModel) -> None:
        super().__init__(targets=[])
        self._client = client

    def resolve(self, spec: ModelSpec, target: str = "langchain") -> ResolvedModel:
        return ResolvedModel(
            provider=spec.provider, target=target, model=spec.model, client=self._client
        )


@dataclass
class FakeSearchTool:
    results: dict[str, Any]
    invoked: bool = field(default=False, init=False)
    last_query: Any = field(default=None, init=False)

    def invoke(self, query: Any) -> dict[str, Any]:
        self.invoked = True
        self.last_query = query
        return self.results


def _fake_tool_registry(search_tool: FakeSearchTool) -> ToolRegistry:
    registry = ToolRegistry()
    registry.register(
        ToolSpec(
            tool_id="web_search",
            name="Web Search",
            description="fake",
            scope=GLOBAL_SCOPE,
            build=lambda: search_tool,
        )
    )
    return registry


def test_news_brief_runs_with_fake_search_and_model() -> None:
    search_results = {
        "results": [
            {"title": "Headline A", "content": "Fact one.", "url": "https://a.example"},
            {"title": "Headline B", "content": "Fact two.", "url": "https://b.example"},
        ]
    }
    search_tool = FakeSearchTool(results=search_results)
    service = RunService(
        model_resolver=FakeModelResolver(FakeChatModel(response="BRIEF: election overview.")),
        tool_registry=_fake_tool_registry(search_tool),
    )

    result = service.run(RunRequest(agent_id="news_brief", input={"topic": "elections"}))

    assert result.status == "completed"
    assert result.error is None
    assert result.output["topic"] == "elections"
    assert result.output["brief"] == "BRIEF: election overview."
    assert result.output["search_results"] == search_results
    assert search_tool.invoked is True
    assert search_tool.last_query == {"query": "elections"}
