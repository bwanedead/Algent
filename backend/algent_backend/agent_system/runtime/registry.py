"""
Runtime selection.

Registers adapters by name and routes ``RunRequest.runtime`` to the matching
implementation. Slice 1 registers only ``LangGraphAdapter`` as the default.
"""

from __future__ import annotations

from collections.abc import Iterable

from algent_backend.agent_system.runs.context import AgentRunContext
from algent_backend.agent_system.runs.models import RunRequest, RunResult

from .base import RuntimeAdapter
from .langgraph import LangGraphAdapter

DEFAULT_RUNTIME = "langgraph"


class RuntimeRegistry:
    """Selects and invokes a runtime adapter."""

    def __init__(self, adapters: Iterable[RuntimeAdapter] | None = None) -> None:
        if adapters is None:
            adapters = [LangGraphAdapter()]
        self._adapters: dict[str, RuntimeAdapter] = {adapter.name: adapter for adapter in adapters}

    def get(self, name: str) -> RuntimeAdapter:
        adapter = self._adapters.get(name)
        if adapter is None:
            known = ", ".join(sorted(self._adapters)) or "(none)"
            raise ValueError(f"Unknown runtime '{name}'. Known runtimes: {known}.")
        return adapter

    def default(self) -> RuntimeAdapter:
        return self.get(DEFAULT_RUNTIME)

    def run(self, request: RunRequest, context: AgentRunContext) -> RunResult:
        return self.get(request.runtime).run(request, context)
