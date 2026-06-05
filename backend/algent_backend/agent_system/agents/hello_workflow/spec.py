"""
Hello workflow metadata.

Owns agent identity, runtime choice, and default model. The graph module reads
these constants; callers reach the agent through ``agent_id`` on ``RunRequest``.
"""

from __future__ import annotations

from algent_backend.agent_system.foundation.models import ModelSpec

AGENT_ID = "hello_workflow"
RUNTIME = "langgraph"
DEFAULT_MODEL = ModelSpec(provider="anthropic", model="claude-sonnet-4-5", temperature=0.2)
