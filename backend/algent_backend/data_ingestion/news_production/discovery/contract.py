"""
``DiscoveryDigest`` — the typed, model-facing output of the ingestion pipeline.

This is the contract a discovery agent (or a human) reads instead of the raw
firehose: a compact, multi-lens stats view of one source batch. Language is the
top axis — every lens is computed *within* a language, never blended across —
because a theme's prominence in Arabic news is its own signal, not noise to be
averaged into the English count.

Pydantic so it round-trips to JSON on disk and validates on the way in.
"""

from __future__ import annotations

from pydantic import BaseModel, Field


class ThemeStat(BaseModel):
    """One theme with its batch frequency and (best-effort) pillar tag."""

    theme: str
    count: int
    pillar: str | None = None


class TonedTheme(BaseModel):
    """One theme ranked by average document tone within a language."""

    theme: str
    avg_tone: float
    count: int
    pillar: str | None = None


class LanguageDigest(BaseModel):
    """The full multi-lens read for a single source language."""

    language: str
    record_count: int
    # Records touching each pillar at least once — the standing-beat coverage.
    pillar_volume: dict[str, int] = Field(default_factory=dict)
    # Lenses.
    top_themes: list[ThemeStat] = Field(default_factory=list)  # volume
    rare_themes: list[ThemeStat] = Field(default_factory=list)  # rarity
    most_negative: list[TonedTheme] = Field(default_factory=list)  # tone
    most_positive: list[TonedTheme] = Field(default_factory=list)


class DiscoveryDigest(BaseModel):
    """A whole source batch, digested. The pipeline's deliverable."""

    source: str  # e.g. "gdelt_gkg"
    batch_id: str  # the source's batch stamp (GKG: 14-digit YYYYMMDDHHMMSS)
    generated_at: str  # ISO-8601 UTC, when this digest was built
    total_records: int
    # The language axis, ordered by record volume (largest first).
    languages: list[LanguageDigest] = Field(default_factory=list)
