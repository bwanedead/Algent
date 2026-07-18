"""
Routing contracts — the generic ranking shapes and the injectable responsibility.

The whole point: the engine is identical everywhere; a ``RoutingBrief`` is the only
thing that makes one router a t1->t2 promoter and another a t2->t3 dispatcher. So
candidates and rankings are deliberately generic (no stage-specific types), and the
brief carries the location-specific job. Swap the brief, reuse the engine.
"""

from __future__ import annotations

from dataclasses import dataclass

from pydantic import BaseModel, Field


class RouteCandidate(BaseModel):
    """A generic item to be ranked — decoupled from any specific stage object.

    A stage-specific adapter (e.g. the promotion router) renders its objects into
    these; the engine never needs to know what they really are.
    """

    id: str
    label: str
    summary: str = ""
    tags: list[str] = Field(default_factory=list)
    signals: dict[str, str | int | float | bool | None] = Field(default_factory=dict)


class RankedChoice(BaseModel):
    """One ranked candidate in a routing decision."""

    candidate_id: str
    rank: int            # 1 = best
    score: float = 0.0   # 0-100 — the router's importance/fit estimate
    rationale: str = ""


class RouteRanking(BaseModel):
    """The router's structured output: an ordered selection, best first."""

    choices: list[RankedChoice] = Field(default_factory=list)
    note: str = ""       # brief: what was set aside / why, if anything


@dataclass(frozen=True)
class RoutingBrief:
    """The injected, location-specific routing responsibility.

    The generic engine is identical at every level of the system; this brief is what
    specializes it. Authoring a new router = writing a brief, not new machinery.
    """

    role: str            # who this router is
    candidate_kind: str  # what the items are
    selecting_for: str   # the ranking criteria
    downstream: str      # what the winner becomes / next steps (self-awareness)
    top_k: int = 10
    # COOLDOWN: things we recently produced, as (when, what). A router that can't see its own
    # recent output re-picks the same story while it dominates the pool. Advisory by design — the
    # router still promotes a genuinely new development on a running story.
    recent: tuple[tuple[str, str], ...] = ()
