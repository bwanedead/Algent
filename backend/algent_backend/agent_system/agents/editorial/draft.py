"""
Draft contracts — the prose product, and the drafter's raw payload.

The drafter is the most autonomous stage: it inherits a promoted treatment (the shape) and
the profile (the evidence), then researches for **precision** — the exact quote, figure, or
detail the profile only pointed at — writes the prose, and hands back anything new it found so
it enriches the profile rather than being lost.

- ``DraftPayload`` is what the model produces: the prose fields + a ``ProfileAdditions`` block
  (its research findings, folded back into the profile at ``stage="drafting"`` so provenance
  records that these arrived after the framing).
- ``ArticleDraft`` is the durable, addressable product the harness finalizes: a stable id,
  citations validated against the (enriched) profile, and lineage back to its treatment and
  profile revision.

Pure contract — no rail imports.
"""

from __future__ import annotations

from pydantic import BaseModel, Field

from algent_backend.agent_system.agents.research.profile import ProfileAdditions

SCHEMA_VERSION = 1


class DraftPayload(BaseModel):
    """What the drafter model returns — prose + the evidence it turned up while writing."""

    title: str = ""
    standfirst: str = ""                # one-line dek: the piece's core in a sentence
    body: str = ""                      # the prose (markdown)
    cited_claim_ids: list[str] = Field(default_factory=list)   # profile claim ids the prose rests on
    cited_source_ids: list[str] = Field(default_factory=list)  # profile source ids the prose attributes to
    research_note: str = ""             # what the drafter went and found (precision research summary)
    additions: ProfileAdditions = Field(default_factory=ProfileAdditions)  # enrich-back into the profile


class ArticleDraft(BaseModel):
    """The durable prose product — lineage-linked to its treatment and profile."""

    id: str
    treatment_id: str = ""
    profile_id: str = ""
    profile_revision: int = 0           # the profile revision the prose was written against
    frame: str = ""                     # the governing frame it was drafted under (from the treatment)

    title: str = ""
    standfirst: str = ""
    body: str = ""
    cited_claim_ids: list[str] = Field(default_factory=list)    # validated against the profile
    cited_source_ids: list[str] = Field(default_factory=list)   # validated against the profile
    research_note: str = ""
    word_count: int = 0

    # ── meta / lineage ──
    schema_version: int = SCHEMA_VERSION
    revision: int = 1                   # bumps each drafting-gauntlet revision (later)
    generated_at: str = ""
    generator: str = ""                 # agent id / version
    model: str = ""
