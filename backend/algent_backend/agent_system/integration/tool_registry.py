"""
Tool registry for agent actions.
"""
from typing import Callable, Dict


Tool = Callable[..., dict]


class ToolRegistry:
    """Registers callable tools accessible to agents."""

    def __init__(self) -> None:
        self._tools: Dict[str, Tool] = {}

    def register(self, name: str, tool: Tool) -> None:
        self._tools[name] = tool

    def get(self, name: str) -> Tool:
        if name not in self._tools:
            raise KeyError(f"tool '{name}' not registered")
        return self._tools[name]

    def list_tools(self) -> list[str]:
        return sorted(self._tools.keys())
