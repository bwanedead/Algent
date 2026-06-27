"""
The research-vector portfolio — the discovery agent's output (the **t1** artifact).

Pipeline terminology: t0 is the deterministic hit list (``DiscoveryPool``); **t1**
is what the discovery agent turns it into — a budgeted set of *research vectors*,
the handoff to the next stage (research). A vector is a *thesis*, not a clipping.
The mapping from hits to vectors is whatever fits: a single hit can be its own
vector (the common case), or several hits can fuse into one when they're truly the
same story or one pattern — 1:1 and many:1 are equally valid, neither is the target.
Effort is allocated across vectors so big forces get depth and the long tail stays
light — high information per unit, not spam.

Pydantic so the agent can emit it as structured output and the next agent can
read it as a typed contract.
"""

from __future__ import annotations

import hashlib

from pydantic import BaseModel, Field

# What kind of thread the vector is — the synthesis "flavors" (see ITERATION_LOG /
# the design discussion): a single-story report, a synthesis weaving several hits
# into one force/theme, a feasible analytic, an implications/scenarios piece, or a
# retrospective tie to past coverage (later, once a story memory exists).
VECTOR_TYPES = ("story", "synthesis", "analytic", "implications", "retrospective")
EFFORT_LEVELS = ("light", "standard", "deep")


class ResearchVector(BaseModel):
    """One thread of importance worth allocating research effort to."""

    # Stable id, assigned in code (not by the model) via ``ensure_vector_ids`` — so a
    # promoted profile's parent_vector_id always points at a real, durable vector.
    id: str = ""
    title: str  # short handle for the thread
    thesis: str  # the angle/claim — the larger force the hits are evidence of
    vector_type: str  # one of VECTOR_TYPES
    rationale: str  # why this is high-leverage / high-signal
    # t0 pool item ids this vector is built from — every claim stays traceable.
    supporting_hits: list[str] = Field(default_factory=list)
    pillars: list[str] = Field(default_factory=list)
    scope: list[str] = Field(default_factory=list)  # countries / languages
    research_effort: str  # one of EFFORT_LEVELS — the budget allocation
    key_questions: list[str] = Field(default_factory=list)  # what research should resolve
    sources: list[str] = Field(default_factory=list)  # URLs the agent surfaced/confirmed


class ResearchPortfolio(BaseModel):
    """The discovery agent's deliverable: a budgeted set of research vectors."""

    generated_at: str
    t0_ref: str | None = None  # which t0 pool this came from
    total_considered: int = 0  # how many t0 hits were triaged
    vectors: list[ResearchVector] = Field(default_factory=list)
    dropped_note: str | None = None  # brief: what was set aside and why (anti-spam record)


def vector_id(vector: ResearchVector) -> str:
    """A deterministic, content-derived id for a vector (same content -> same id)."""
    seed = f"{vector.title}\n{vector.thesis}".strip()
    return "vec_" + hashlib.sha1(seed.encode("utf-8")).hexdigest()[:10]


def ensure_vector_ids(portfolio: ResearchPortfolio) -> ResearchPortfolio:
    """Fill any empty vector id with a stable content-derived id. Idempotent.

    Ids are assigned in code, not by the model — collision-resistant and stable, so a
    profile's ``parent_vector_id`` always references a real, durable vector id.
    """
    vectors = [v if v.id else v.model_copy(update={"id": vector_id(v)}) for v in portfolio.vectors]
    return portfolio.model_copy(update={"vectors": vectors})
