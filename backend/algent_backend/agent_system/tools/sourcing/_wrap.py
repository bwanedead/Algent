"""
Helper that wraps a plain Python function as a LangChain ``StructuredTool``.

Several sourcing vendors (Brave, GDELT, RSS, Firecrawl, xAI) are reached over
plain REST/parsing rather than a prebuilt LangChain integration. Wrapping them
gives every tool in the portfolio the same surface — ``.invoke({...})`` now, and
``bind_tools`` compatibility later — regardless of how it is implemented.

Lazy import on purpose: building a tool is the moment the rail dependency loads.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any


def as_structured_tool(func: Callable[..., Any], *, name: str, description: str) -> Any:
    """Wrap ``func`` as a LangChain ``StructuredTool`` (schema from type hints)."""
    from langchain_core.tools import StructuredTool

    return StructuredTool.from_function(func=func, name=name, description=description)
