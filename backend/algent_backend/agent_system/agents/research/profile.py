"""
t2 contracts — the SignalProfile and its parts (the newsroom's central asset).

A *signal profile* is the researched knowledge object a t1 signal vector is promoted
into: a **claim ledger** + a **source ledger** + situational modules, every piece
stably-IDed so it can later be indexed into the signal graph. An article — and every
other t3 production — is a *view* of this object, not the object itself.

Graph-ready by design (stable IDs, parent vector id, entity tags, version stamps, and
empty ``derived_leads`` / ``corpus_context`` slots for the future feedback loop) but
DB-agnostic: it round-trips to JSON and is persisted through ``ProfileStore``. No
storage or rail imports here — pure contract.
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field

SCHEMA_VERSION = 1

# A claim's legitimacy plane — the heart of "confirmed here, speculative there".
ClaimStatus = Literal[
    "confirmed", "likely", "unconfirmed", "contested", "speculative", "opinion"
]
SourceType = Literal["primary", "secondary", "tertiary"]
# Not every profile ends "article-ready" — some honestly end as "not enough here".
ProfileStatus = Literal[
    "draft", "researching", "complete", "needs_verification",
    "insufficient_evidence", "superseded", "archived",
]
# What a finished profile thinks it can feed (the t3 lane reads these later).
SuggestedUse = Literal[
    "radar", "article", "brief", "video", "audio", "chart", "watch",
    "archive", "needs_verification",
]
# What a backfeed lead is good for — a lead's own (smaller) vocabulary.
LeadUse = Literal["radar", "profile", "background", "watch"]


class SourceSnapshot(BaseModel):
    """Point-in-time tamper-evidence for a cited source.

    Hash + timestamp prove what the source said when we used it (and catch later
    external edits / link-rot). The full captured text lives as a separate artifact
    (``full_text_path``) so the ledger stays small and readable — only a short
    ``excerpt`` is inline.
    """

    content_hash: str = ""        # hash of the captured content at use-time
    captured_at: str = ""         # ISO-8601 UTC
    excerpt: str = ""             # short inline snippet for readability
    full_text_path: str | None = None  # the full captured text, stored by reference


class SourceArtifact(BaseModel):
    """One exact cited thing — an article / PDF / post / filing / transcript / dataset.

    This is the *artifact* (a specific URL/document), not the permanent source
    identity. ``publisher_id`` / ``author_id`` are reserved hooks for when a
    SourceOrg / SourcePerson registry exists; null for now.
    """

    id: str
    url: str = ""
    title: str = ""
    publisher: str = ""
    author: str = ""
    publisher_id: str | None = None  # future: link to a SourceOrg registry
    author_id: str | None = None     # future: link to a SourcePerson registry
    source_type: SourceType = "secondary"
    published_at: str = ""
    retrieved_at: str = ""
    reliability: str = ""            # free-text note now; a score later
    independent_of: list[str] = Field(default_factory=list)  # source ids it is NOT reposting
    safe_to_cite: bool = True
    snapshot: SourceSnapshot | None = None


class Claim(BaseModel):
    """One atomic, checkable assertion — graded, and traced to sources by reference."""

    id: str
    text: str
    status: ClaimStatus = "unconfirmed"
    supported_by: list[str] = Field(default_factory=list)     # SourceArtifact ids
    contradicted_by: list[str] = Field(default_factory=list)  # SourceArtifact ids
    note: str = ""


class DerivedLead(BaseModel):
    """A rich adjacent lead noticed mid-research — backfeed into the T0 lead pool.

    Any research stage may emit one when it spots something worth its own future
    attention. It NEVER mutates t1 directly; the next synthesis decides whether to
    promote / merge / archive it.
    """

    id: str
    title: str
    why_noticed: str = ""
    source_url: str = ""
    source_artifact_id: str | None = None
    excerpt: str = ""
    relation_to_profile: str = ""
    suggested_use: LeadUse = "profile"
    confidence: str = ""            # free-text now (low / med / high)
    entities: list[str] = Field(default_factory=list)
    topics: list[str] = Field(default_factory=list)
    lead_origin: str = "research_backfeed"
    created_by_stage: str = ""


class ProfileModules(BaseModel):
    """Situational profile sections — all optional. Core ledgers are stable; these vary."""

    timeline: list[str] = Field(default_factory=list)
    angles: list[str] = Field(default_factory=list)
    omissions: list[str] = Field(default_factory=list)        # what's missing / counter-framing
    open_questions: list[str] = Field(default_factory=list)
    data_notes: list[str] = Field(default_factory=list)       # stats/datasets worth crunching
    visual_opportunities: list[str] = Field(default_factory=list)  # charts/maps a production could use
    watch_triggers: list[str] = Field(default_factory=list)   # what to monitor for updates


class SignalProfile(BaseModel):
    """t2 — the researched knowledge object (the asset). An article is a view of this."""

    id: str
    parent_vector_id: str = ""       # the t1 signal vector this was promoted from
    title: str
    summary: str = ""
    profile_status: ProfileStatus = "draft"

    claim_ledger: list[Claim] = Field(default_factory=list)
    source_ledger: list[SourceArtifact] = Field(default_factory=list)
    entities: list[str] = Field(default_factory=list)         # graph tags
    modules: ProfileModules = Field(default_factory=ProfileModules)

    # What the profile believes it can feed downstream (the t3 lane reads these).
    output_recommendations: list[SuggestedUse] = Field(default_factory=list)

    # Graph-loop slots — present but empty until backfeed / self-search exist.
    derived_leads: list[DerivedLead] = Field(default_factory=list)
    corpus_context: list[str] = Field(default_factory=list)

    # Provenance / versioning — the manifest seed; eases later audit + migration.
    schema_version: int = SCHEMA_VERSION
    revision: int = 1
    generated_at: str = ""           # ISO-8601 UTC
    generator: str = ""              # agent id / version that built it
    model: str = ""                  # model that produced it
