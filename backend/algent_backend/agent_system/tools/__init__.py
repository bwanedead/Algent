"""
Tool layer.

Algent owns tool selection and scoping; concrete tools (the first one backed by
LangChain) build themselves behind ``ToolSpec.build``. ``ToolRegistry`` resolves
which tools an agent may use.
"""

from .registry import ToolRegistry, default_tool_registry
from .resolved import ResolvedTools
from .spec import GLOBAL_SCOPE, ToolSpec, agent_scope, family_scope

__all__ = [
    "GLOBAL_SCOPE",
    "ResolvedTools",
    "ToolRegistry",
    "ToolSpec",
    "agent_scope",
    "default_tool_registry",
    "family_scope",
]
