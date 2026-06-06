"""
Run context — platform services handed into execution.

Keeps runtimes from inventing their own way to reach shared services. Carries the
run id, the model resolver, and the concrete tools resolved for this agent.
Artifact writer, events, and secrets come later.

Stays neutral: it must not import LangChain/LangGraph. ``tools`` is a read-only
mapping of tool id -> concrete tool; its concrete types are intentionally ``Any``.
The mapping may build tools lazily on access (see ``tools.ResolvedTools``), so the
context only depends on the neutral ``Mapping`` shape, not the implementation.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from typing import Any

from algent_backend.agent_system.foundation.models import ModelResolver


@dataclass(frozen=True)
class AgentRunContext:
    """Environment available to a running agent."""

    run_id: str
    model_resolver: ModelResolver
    tools: Mapping[str, Any] = field(default_factory=dict)
