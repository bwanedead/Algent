"""
Run context — platform services handed into execution.

Keeps runtimes from inventing their own way to reach shared services. Slice 1
carries only run id and model resolver; artifact writer, events, and secrets
come later.
"""

from __future__ import annotations

from dataclasses import dataclass

from algent_backend.agent_system.foundation.models import ModelResolver


@dataclass(frozen=True)
class AgentRunContext:
    """Environment available to a running agent."""

    run_id: str
    model_resolver: ModelResolver
