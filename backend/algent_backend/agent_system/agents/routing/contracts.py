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
    rank: int            # 1 = best among *eligible* promote order after cooldown sort
    score: float = 0.0   # 0-100 — the router's importance/fit estimate
    rationale: str = ""
    # Agent semantic judgment: same story-family as a recent published headline.
    cooldown: bool = False
    cooldown_reason: str = ""  # which prior headline / why, if cooldown


class RouteRanking(BaseModel):
    """The router's structured output: full ordered list, best first.

    Every input candidate should appear once. Cooldown flags are agent judgment
    (not lexical). Promote the first choice with ``cooldown=False``.
    """

    choices: list[RankedChoice] = Field(default_factory=list)
    note: str = ""       # brief: what was set aside / cooldown summary


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
    # Rank ALL candidates when True (promotion default). When False, cap at top_k.
    rank_all: bool = True
    top_k: int = 50      # only used when rank_all is False; also a soft max for huge sets
    # COOLDOWN payload: recent published (when, title). Agent judges story-family match.
    recent: tuple[tuple[str, str], ...] = ()
