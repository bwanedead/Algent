"""
Discovery output contracts — the handoff to downstream agents.

Unlike ``AgentSpec`` (an in-process recipe), these are serializable wire
contracts: a discovery run writes a ``DiscoveryResult`` artifact, and each
``TopicCandidate`` is what a downstream research/brief agent later consumes as
its topic. Kept small on purpose; fields earn their place as the pipeline grows.
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field

Significance = Literal["low", "medium", "high"]
# Where a candidate should flow next. "brief" = write a grounded brief now;
# "investigate" = deeper research warranted; "fast_update" = live/breaking, wants
# quick current coverage. Routing on this is downstream and deferred.
SuggestedRoute = Literal["brief", "investigate", "fast_update"]


class TopicCandidate(BaseModel):
    """One item discovery judged worth deeper work."""

    title: str
    why_notable: str
    significance: Significance = "medium"
    category: str | None = None
    seed_sources: list[str] = Field(default_factory=list)
    suggested_route: SuggestedRoute = "brief"


class DiscoveryResult(BaseModel):
    """The output of one discovery run. ``candidates`` may be empty."""

    candidates: list[TopicCandidate] = Field(default_factory=list)
    notes: str | None = None


def cap_candidates(result: DiscoveryResult, limit: int) -> DiscoveryResult:
    """Mechanically enforce the candidate cap, preserving the model's ordering.

    The prompt asks the model to be selective; this is the backstop so a run can
    never emit more than ``limit`` candidates regardless of model behavior.
    """
    if limit < 0:
        limit = 0
    return DiscoveryResult(candidates=result.candidates[:limit], notes=result.notes)
