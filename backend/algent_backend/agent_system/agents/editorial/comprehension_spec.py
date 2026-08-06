"""
Comprehension-reviewer agent definition — the naive-reader lane (gate C).

Reads the finished prose cold, as its intended general reader, and reports where the ramp is
missing or the molecule arrives without its bonds. Tool-free, nano tier (one structured read).
Rail-free: the graph builder lives in ``comprehension_loop.py``.
"""

from __future__ import annotations

from typing import Any

from algent_backend.agent_system.agents.agent_spec import AgentSpec
from algent_backend.agent_system.foundation.models import house_spec
from algent_backend.agent_system.runs.context import AgentRunContext

from .comprehension_loop import build_comprehension_reviewer_graph

AGENT_ID = "comprehension_reviewer"
RUNTIME = "langgraph"
FAMILY = "newsroom"

# A single cold read of the prose — nano is plenty (and reading as a *normal* reader, not an
# expert, is the job; a bigger model would be more likely to fill gaps a real reader can't).
DEFAULT_MODEL = house_spec(reasoning_effort="low", temperature=0.3)


def build_graph(context: AgentRunContext) -> Any:
    return build_comprehension_reviewer_graph(context, model_spec=DEFAULT_MODEL)


SPEC = AgentSpec(
    agent_id=AGENT_ID,
    name="Comprehension Reviewer",
    runtime=RUNTIME,
    build_graph=build_graph,
    description="Reads the finished prose cold as its general reader; flags missing ramps / broken threads.",
    default_model=DEFAULT_MODEL,
    family=FAMILY,
    tool_ids=(),
    search_channels=None,
    test_fixture=None,   # needs a draft; exercised via the pipeline / unit tests
)
