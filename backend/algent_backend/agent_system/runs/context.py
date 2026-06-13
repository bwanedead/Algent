"""
Run context — platform services handed into execution.

Keeps runtimes from inventing their own way to reach shared services. Carries
the run id, the model resolver, the concrete tools resolved for this agent, an
event sink, and the artifact writer.

Stays neutral: it must not import LangChain/LangGraph, agents, runtime, or
tools packages. ``tools`` is a read-only mapping of tool id -> concrete tool;
concrete types are intentionally ``Any``. ``emit`` is a plain callable so the
context does not depend on the control plane — the harness binds it to the
run's recorder; the default is a no-op so contexts are cheap to build in tests.
"""

from __future__ import annotations

from collections.abc import Callable, Mapping
from dataclasses import dataclass, field
from typing import Any

from algent_backend.agent_system.artifacts import ArtifactWriter
from algent_backend.agent_system.foundation.models import ModelResolver

EventSink = Callable[[str, dict[str, Any]], None]


def _noop_emit(event_type: str, payload: dict[str, Any] | None = None) -> None:
    """Default sink: events go nowhere unless the harness wires a recorder."""


@dataclass(frozen=True)
class AgentRunContext:
    """Environment available to a running agent."""

    run_id: str
    model_resolver: ModelResolver
    tools: Mapping[str, Any] = field(default_factory=dict)
    emit: EventSink = _noop_emit
    artifacts: ArtifactWriter | None = None
