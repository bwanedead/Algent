"""
Neutral run contracts.

These types describe what Algent asks a runtime to do and what comes back. They
deliberately avoid LangGraph shapes, event streams, or artifact references — those
arrive in later slices.
"""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field

RunStatus = Literal["completed", "failed"]


class RunRequest(BaseModel):
    """Request to execute an agent through a runtime rail."""

    agent_id: str
    input: dict[str, Any]
    runtime: str = "langgraph"


class RunResult(BaseModel):
    """Outcome of a single agent run."""

    run_id: str
    agent_id: str
    runtime: str
    status: RunStatus
    output: dict[str, Any] = Field(default_factory=dict)
    error: str | None = None
