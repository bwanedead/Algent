"""
Neutral run contracts.

These types describe what Algent asks a runtime to do and what comes back. They
deliberately avoid LangGraph shapes — rail specifics live in runtime adapters.
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
    # Pre-allocated run id (the CLI allocates one before spawning a background
    # child so watchers can attach immediately). None = service generates one.
    run_id: str | None = None
    # Turn budget — a mechanical leash on agent loops, enforced by the runtime
    # adapter. None = the rail's default limit.
    max_turns: int | None = None


class RunResult(BaseModel):
    """Outcome of a single agent run."""

    run_id: str
    agent_id: str
    runtime: str
    status: RunStatus
    output: dict[str, Any] = Field(default_factory=dict)
    error: str | None = None
