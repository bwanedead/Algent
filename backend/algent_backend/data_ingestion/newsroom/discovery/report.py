"""
The discovery pipeline's output artifacts — what the next (agentic) layer reads.

Two deliverables, deliberately separate:

- :class:`InsightsReport` — the *deterministic* finds: a ranked candidate list
  (themes and entities) carrying their signals (velocity, cross-language reach,
  novelty, tone), plus a per-language "world news" view. This is the spine.
- :class:`LongtailSample` — a small, language-stratified slice of *raw* records,
  produced after the deterministic pass so an agent can sift it for anything the
  stats missed and decide whether it earns a place on the list or gets tossed.

Pydantic so both round-trip to JSON on disk and validate on the way in.
"""

from __future__ import annotations

from pydantic import BaseModel, Field


class Candidate(BaseModel):
    """One ranked discovery candidate (a theme or a named entity)."""

    key: str  # the theme code or entity name
    kind: str  # "theme" | "person" | "organization"
    pillar: str | None = None
    count: int  # records mentioning it this batch
    # Acceleration vs the rolling baseline: (count - baseline) / (baseline + k).
    # None on the first run, before any history exists.
    velocity: float | None = None
    rising: bool = False
    novel: bool = False  # unseen in recent memory
    language_count: int = 0
    languages: list[str] = Field(default_factory=list)
    avg_tone: float | None = None
    source_spread: int = 0  # distinct outlets carrying it
    score: float = 0.0
    reasons: list[str] = Field(default_factory=list)  # why it made the cut
    # Co-occurring candidates folded into this one (the story's other entities).
    related: list[str] = Field(default_factory=list)
    # Example article URLs from the supporting records (free-fetchable grounding).
    examples: list[str] = Field(default_factory=list)


class LanguageInsights(BaseModel):
    """The "world news" view for one source language: what's big in that domain."""

    language: str
    record_count: int
    top: list[str] = Field(default_factory=list)  # biggest candidate keys here
    rising: list[str] = Field(default_factory=list)  # of those, globally rising/novel


class InsightsReport(BaseModel):
    """The deterministic discovery artifact for one source batch."""

    source: str
    batch_id: str
    generated_at: str  # ISO-8601 UTC
    total_records: int
    # False on the very first run (no prior batches) — velocity is unavailable.
    has_velocity_baseline: bool = False
    candidates: list[Candidate] = Field(default_factory=list)
    by_language: list[LanguageInsights] = Field(default_factory=list)


class SampleRecord(BaseModel):
    """One raw record in the long-tail slice, trimmed to what an agent needs."""

    lang: str
    ngram: str
    text: str  # the surrounding snippet (pre … post)
    url: str


class LongtailSample(BaseModel):
    """A language-stratified random slice of raw records — the anti-rut input."""

    source: str
    batch_id: str
    generated_at: str
    size: int
    languages: int  # distinct languages represented in the slice
    records: list[SampleRecord] = Field(default_factory=list)


class BeatHit(BaseModel):
    """One article matching a beat's targeted query."""

    title: str
    url: str
    domain: str = ""
    country: str = ""
    language: str = ""
    seendate: str = ""


class BeatResult(BaseModel):
    """The outcome of sweeping one beat — its hits, or the error that stopped it."""

    beat_id: str
    label: str
    kind: str  # "pillar" | "country"
    pillar: str | None = None
    country: str | None = None
    query: str
    hit_count: int = 0
    hits: list[BeatHit] = Field(default_factory=list)
    error: str | None = None  # set if the beat failed (e.g. rate-limited out)
    # When this beat was last fetched successfully (ISO-8601 UTC). Empty on a failed
    # sweep and on sheets written before per-beat freshness existed — both read as
    # "infinitely stale", which is the safe default: refresh it, don't serve it.
    swept_at: str = ""


class BeatSheet(BaseModel):
    """A full targeted sweep across the beat registry — the faceted hit sheet.

    Tagged, not bucketed: each hit carries the beat's pillar/country tags, so the
    downstream layer slices (economics, country:DE, …) on demand.
    """

    generated_at: str
    timespan: str
    beats_swept: int
    beats_failed: int
    total_hits: int
    results: list[BeatResult] = Field(default_factory=list)
    # The request gap the last sweep ended on. Carried so the next sweep starts where
    # the limiter actually left us instead of re-learning by sacrificing its first few
    # beats — which starved whichever beat sorts first in the registry (see sweep.py).
    last_gap_s: float = 0.0
    # When DOC last throttled us (ISO-8601 UTC). Empty when the last sweep saw no
    # rate_limited responses. Paired with ``last_gap_s`` so the next refresh can refuse
    # to touch DOC until the known cooldown has elapsed — asking earlier is how we
    # walk into a limit we already know about.
    last_throttle_at: str = ""
    # True when the last sweep stopped early because consecutive throttles said DOC
    # was locked; remaining beats were left unswept on purpose.
    aborted_for_throttle: bool = False


class PoolItem(BaseModel):
    """One consolidated discovery candidate — the unit the synthesis agent reads.

    A common shape over both channels: the GKG net contributes signal-rich
    information objects (velocity / novelty / cross-language, entity context); the
    DOC sweep contributes grounded article hits (titles + URLs). Tagged, not
    bucketed — the agent weaves these into research vectors.
    """

    id: str
    label: str
    channel: str  # "gkg" | "beat"
    kind: str  # "theme" | "person" | "organization" | "article"
    pillars: list[str] = Field(default_factory=list)
    scope: list[str] = Field(default_factory=list)  # countries and/or languages
    signals: dict[str, float | int | bool | str | None] = Field(default_factory=dict)
    evidence: list[BeatHit] = Field(default_factory=list)  # grounding articles (URLs)
    related: list[str] = Field(default_factory=list)  # co-occurring members (GKG)


class DiscoveryPool(BaseModel):
    """The **t0** artifact — the first output of the discovery pipeline.

    Official terminology: ``t0`` is the deterministic pipeline's initial artifact
    (this consolidated, tagged, grounded hit list) and the **t0 payload** is the
    initial input handed to the agent layer. The term is pipeline-relative — each
    pipeline's first deliverable is its own t0 — and the downstream agent artifacts
    follow as t1 (the research-vector portfolio), t2 (research briefs), etc.

    Everything we sensed this cycle from both channels, organized so judgment can
    be applied — not yet judged.
    """

    generated_at: str
    gkg_batch_id: str | None = None
    beat_sheet_at: str | None = None
    item_count: int = 0
    by_channel: dict[str, int] = Field(default_factory=dict)
    by_pillar: dict[str, int] = Field(default_factory=dict)
    facets: dict[str, list[str]] = Field(default_factory=dict)  # pillar -> item ids
    items: list[PoolItem] = Field(default_factory=list)
