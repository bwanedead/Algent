"""
AgentSpec — the in-process recipe for an agent.

This is a Python-callable-carrying recipe (it holds ``build_graph``), not a
serializable wire contract. That is why it is a frozen dataclass and not a
Pydantic model: it is meant to be constructed in code and handed around in
process. If a serializable UI/GraphOS description is needed later, introduce a
separate ``AgentManifest`` rather than overloading this.

``AgentSpec`` stays neutral about the rail: ``build_graph`` returns ``Any`` and
this module never imports LangGraph types. The runtime adapter for the agent's
declared ``runtime`` knows how to execute whatever ``build_graph`` returns.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

from algent_backend.agent_system.foundation.models import ModelSpec
from algent_backend.agent_system.runs.context import AgentRunContext


@dataclass(frozen=True)
class TestFixture:
    """A saved input that runs this agent in ISOLATION (see backend/fixtures/).

    Lets `runs start <agent> --fixture` feed the agent a stored upstream artifact
    instead of producing it — so a stage is testable without spending on everything
    before it. The fixture lives *with* the agent so it can't drift from a doc table.
    """

    input_file: str            # path to the JSON fixture (relative to backend/)
    input_key: str | None = None  # state key to mount it under (None = whole input dict)


@dataclass(frozen=True)
class AgentSpec:
    """A reusable recipe for one agent."""

    agent_id: str
    name: str
    runtime: str
    build_graph: Callable[[AgentRunContext], Any]
    description: str | None = None
    default_model: ModelSpec | None = None
    family: str | None = None
    tool_ids: tuple[str, ...] = ()
    # Hard per-agent gate on the web_search facade's API channels (keyword,
    # semantic, read, rich, x). None = the safe default (free/cheap only; paid
    # `rich`/`x` off). The runtime scopes the facade's policy to this per run.
    search_channels: tuple[str, ...] | None = None
    # Stored input for isolated testing via `runs start <agent> --fixture`.
    test_fixture: TestFixture | None = None
