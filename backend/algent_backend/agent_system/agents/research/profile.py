"""
t2 contracts — the research profile and its parts (the newsroom's central asset).

A *profile* is the researched knowledge object a t1 research vector is promoted into,
and — crucially — an **agent-facing interface**: it must be easy for an agent to build
reliably, read holistically, and extend later. So it is a flat set of self-contained,
addressable items (claims, threads, entities, sources), each with a stable id, light
provenance, and a salience — append-friendly, retrievable, graph-ready.

Three layers of knowledge, kept distinct so a consumer can trust each appropriately:
- EVIDENCE SPINE (verifiable): the claim ledger + source ledger.
- KNOWLEDGE FIELD (organic richness): entities (the graph join-keys) + threads (flexible
  strands of the surrounding field — no rigid rings, no imposed degrees).
- META-KNOWLEDGE (what we don't know): omissions, open questions.

The raw object here is CANONICAL. A separate deterministic renderer (``briefing.py``)
produces a readable *view*; it is never the source of truth. Pure contract — no storage
or rail imports; round-trips to JSON, persisted through ``ProfileStore``.
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field

SCHEMA_VERSION = 2

# A claim's legitimacy plane — the heart of "confirmed here, speculative there".
ClaimStatus = Literal[
    "confirmed", "likely", "unconfirmed", "contested", "speculative", "opinion"
]
SourceType = Literal["primary", "secondary", "tertiary"]
# How much an item matters — for renderer ordering and (later) RAG retrieval priority.
Salience = Literal["high", "medium", "low"]
# How well-grounded a claim/thread is — HARNESS-computed from snapshots, not the model.
# snapshotted = backed by a source we deep-read & hashed; snippet_only = sourced but only
# from search snippets (no deep read); unsourced = no source at all.
GroundingStatus = Literal["snapshotted", "snippet_only", "unsourced"]
# The profile lifecycle. The first research pass yields a "draft"; "mature" is EARNED
# by surviving the review/enrichment gauntlet — not just by having a first pass.
ProfileStatus = Literal[
    "draft", "researching", "reviewed_needs_enrichment", "enriching",
    "needs_verification", "complete", "mature",
    "insufficient_evidence", "unsound", "superseded", "archived",
]
# What a finished profile thinks it can feed (the t3 lane reads these later).
SuggestedUse = Literal[
    "radar", "article", "brief", "video", "audio", "chart", "watch",
    "archive", "needs_verification",
]
# What a backfeed lead is good for — a lead's own (smaller) vocabulary.
LeadUse = Literal["radar", "profile", "background", "watch"]


class ItemProvenance(BaseModel):
    """Light provenance on an individual item — traceable contributions + upgrades."""

    added_by_stage: str = ""   # the research stage/agent that added it
    revision: int = 1          # the profile revision it was added/updated in
    created_at: str = ""       # ISO-8601 UTC


class SourceSnapshot(BaseModel):
    """Point-in-time tamper-evidence for a cited source (harness-captured, never model).

    Hash + timestamp prove what the source said when we used it (and catch later
    external edits / link-rot). The full captured text lives as a separate artifact
    (``full_text_path``); only a short ``excerpt`` is inline.
    """

    content_hash: str = ""
    captured_at: str = ""
    excerpt: str = ""
    full_text_path: str | None = None


class SourceArtifact(BaseModel):
    """One exact cited thing — an article / PDF / post / filing / transcript / dataset.

    The id is content-addressed (from the normalized URL) by the harness, so the *same*
    source has the same id everywhere — the cross-profile join-key, dedup-friendly.
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
    provenance: ItemProvenance | None = None


class Entity(BaseModel):
    """A first-class node in the knowledge field — the graph join-key.

    The id is content-addressed (normalized ``canonical_name`` + ``type``) so the same
    entity links across profiles. Humble for now: no resolution system — ``aliases``
    and ``canonical_name`` leave room to get smarter later.
    """

    id: str
    name: str
    canonical_name: str = ""        # resolved canonical form (= name for now)
    type: str = "other"             # person | org | place | concept | event | other (open)
    role: str = ""                  # freeform — its role in THIS story
    aliases: list[str] = Field(default_factory=list)


class Claim(BaseModel):
    """One atomic, checkable assertion — graded, and traced to sources by reference."""

    id: str
    text: str
    status: ClaimStatus = "unconfirmed"
    salience: Salience = "medium"
    grounding: GroundingStatus = "unsourced"  # HARNESS-computed from snapshots, not the model
    supported_by: list[str] = Field(default_factory=list)     # SourceArtifact ids
    contradicted_by: list[str] = Field(default_factory=list)  # SourceArtifact ids
    note: str = ""
    provenance: ItemProvenance | None = None


class Thread(BaseModel):
    """A flexible strand of the surrounding knowledge field — the organic richness.

    NOT a ring or a fixed degree: the agent records as many threads as the story
    genuinely has, of whatever ``kind`` each actually is. Each links the entities,
    claims, and sources it touches, so it is grounded *and* graph-ready connective
    tissue — and a natural retrieval unit.
    """

    id: str
    title: str
    kind: str = ""              # OPEN hint: background | force | connection | framing | implication | analysis | ...
    body: str = ""              # freeform — the actual richness / dot-connecting
    salience: Salience = "medium"
    grounding: GroundingStatus = "unsourced"  # HARNESS-computed: the weakest of its claims
    entities: list[str] = Field(default_factory=list)   # entity ids it touches
    claims: list[str] = Field(default_factory=list)     # claim ids that ground it
    sources: list[str] = Field(default_factory=list)    # source ids
    provenance: ItemProvenance | None = None


class DerivedLead(BaseModel):
    """A rich adjacent lead noticed mid-research — backfeed into the T0 lead pool.

    Never mutates t1 directly; the next synthesis decides promote / merge / archive.
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


class ProfileAdditions(BaseModel):
    """What an enricher contributes to an existing profile — ADDITIVE only.

    The enricher authors new items with LOCAL ids (and may reference existing item ids
    from the briefing to link). The merge harness folds these in: content-addressed dedup
    collapses anything already present, refs are rewritten, snapshots attach to the new
    reads, the revision bumps, and grounding is recomputed.
    """

    sources: list[SourceArtifact] = Field(default_factory=list)
    claims: list[Claim] = Field(default_factory=list)
    threads: list[Thread] = Field(default_factory=list)
    entities: list[Entity] = Field(default_factory=list)
    omissions: list[str] = Field(default_factory=list)
    open_questions: list[str] = Field(default_factory=list)
    addressed_findings: list[str] = Field(default_factory=list)  # review finding ids this resolved
    note: str = ""


class SignalProfile(BaseModel):
    """t2 — the researched knowledge object (the asset). An article is a view of this.

    A flat, addressable, agent-ergonomic interface. The model authors items with simple
    LOCAL ids (s1, c1, e1, t1); the harness assigns stable/content-addressed ids and
    rewrites references (see ``assembly.py``).
    """

    id: str
    parent_vector_id: str = ""       # the t1 research vector this was promoted from
    title: str
    summary: str = ""                # the holistic gist (read first)
    profile_status: ProfileStatus = "draft"
    as_of: str = ""                  # recency horizon of the info (latest date it reflects)

    # ── evidence spine (verifiable) ──
    source_ledger: list[SourceArtifact] = Field(default_factory=list)
    claim_ledger: list[Claim] = Field(default_factory=list)

    # ── knowledge field (organic richness) ──
    entities: list[Entity] = Field(default_factory=list)
    threads: list[Thread] = Field(default_factory=list)

    # ── meta-knowledge (what we don't know) ──
    omissions: list[str] = Field(default_factory=list)        # what's missing / counter-framing
    open_questions: list[str] = Field(default_factory=list)
    timeline: list[str] = Field(default_factory=list)         # chronology, when it helps

    # ── forward / applicability ──
    output_recommendations: list[SuggestedUse] = Field(default_factory=list)
    data_notes: list[str] = Field(default_factory=list)       # stats/datasets to crunch (analytics lane)
    visual_opportunities: list[str] = Field(default_factory=list)  # charts/maps a production could use
    watch_triggers: list[str] = Field(default_factory=list)   # what to monitor for a refresh
    derived_leads: list[DerivedLead] = Field(default_factory=list)
    related_profiles: list[str] = Field(default_factory=list)  # graph edges (corpus; empty now)
    corpus_context: list[str] = Field(default_factory=list)    # what we already knew (empty now)

    # ── provenance / versioning (manifest seed) ──
    schema_version: int = SCHEMA_VERSION
    revision: int = 1
    generated_at: str = ""           # when this profile was built
    generator: str = ""              # agent id / version that built it
    model: str = ""                  # model that produced it
