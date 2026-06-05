"""
Runtime selection.

Registers adapters by name and hands the matching implementation to callers.
Orchestration lives in ``RunService``; this registry stays focused on lookup and
does not know concrete agents.
"""

from __future__ import annotations

from collections.abc import Iterable

from .base import RuntimeAdapter
from .langgraph import LangGraphAdapter

DEFAULT_RUNTIME = "langgraph"


class RuntimeRegistry:
    """Selects a runtime adapter by name."""

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
