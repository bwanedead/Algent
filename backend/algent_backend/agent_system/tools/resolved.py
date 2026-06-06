"""
ResolvedTools — a lazy, read-only mapping of an agent's tools.

A tool is *available* to an agent as soon as it resolves by scope, but it is only
*built* when the agent actually accesses it. This keeps a no-tool agent from
paying for (or requiring credentials for) tools it never touches, even though
global tools resolve for every agent.

The built object is cached, so repeated access in a run builds once.
"""

from __future__ import annotations

from collections.abc import Iterator, Mapping
from typing import Any

from .spec import ToolSpec


class ResolvedTools(Mapping[str, Any]):
    """Maps tool id -> concrete tool, building lazily on first access."""

    def __init__(self, specs: list[ToolSpec]) -> None:
        self._specs: dict[str, ToolSpec] = {spec.tool_id: spec for spec in specs}
        self._built: dict[str, Any] = {}

    def __getitem__(self, tool_id: str) -> Any:
        if tool_id not in self._built:
            if tool_id not in self._specs:
                raise KeyError(tool_id)
            self._built[tool_id] = self._specs[tool_id].build()
        return self._built[tool_id]

    def __contains__(self, tool_id: object) -> bool:
        # Membership must not trigger a build.
        return tool_id in self._specs

    def __iter__(self) -> Iterator[str]:
        return iter(self._specs)

    def __len__(self) -> int:
        return len(self._specs)
