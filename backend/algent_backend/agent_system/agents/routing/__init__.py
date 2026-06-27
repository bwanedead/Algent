"""Routing — a generic, brief-driven ranking/selection capability.

Reusable at any level of the newsroom (t1->t2 promotion now; t2->t3 dispatch and
sub-routers later) by injecting a different ``RoutingBrief`` into the same stateless
engine. Authoring a router = a brief + a candidate adapter, never new machinery.
"""

from __future__ import annotations

from .contracts import RankedChoice, RouteCandidate, RouteRanking, RoutingBrief
from .engine import ROUTING_DECISION, route
from .promotion import PROMOTION_BRIEF, rank_portfolio, top_vector

__all__ = [
    "PROMOTION_BRIEF",
    "ROUTING_DECISION",
    "RankedChoice",
    "RouteCandidate",
    "RouteRanking",
    "RoutingBrief",
    "rank_portfolio",
    "route",
    "top_vector",
]
