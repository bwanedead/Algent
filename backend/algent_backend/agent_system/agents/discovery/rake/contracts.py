"""
Rake contracts — the nano scout's per-chunk verdict shape.

The rake stage is a *filter*, not a judge: each verdict says only "is this a real,
newsworthy lead, or obvious spam/promo/boilerplate/non-news to toss before the
pricier synthesis model looks at it". Kept simple on purpose — surface-level
pruning, one line of reasoning per item, no vector-building (that's t1's job).
"""

from __future__ import annotations

from pydantic import BaseModel, Field


class RakeVerdict(BaseModel):
    """Keep-or-toss for one t0 pool item, by its id."""

    id: str  # the pool item id this verdict is about (echo it exactly)
    keep: bool  # True = a real newsworthy lead worth the synthesis model's time
    reason: str = ""  # one short line — why kept or tossed


class RakeChunkResult(BaseModel):
    """The scout's verdicts for one chunk of the pool."""

    verdicts: list[RakeVerdict] = Field(default_factory=list)


class RakeSummary(BaseModel):
    """What the rake stage did to the pool — for the timeline and the audit."""

    considered: int = 0  # rakeable items (excludes pre-vetted passthrough)
    kept: int = 0
    dropped: int = 0
    pre_vetted: int = 0  # items that skipped rake (already LLM-vetted, e.g. X)
    chunks: int = 0
    estimated_usd: float = 0.0
    dropped_examples: list[str] = Field(default_factory=list)  # "label — reason"
