"""
Review contracts — the profile reviewer's output: a task-generating critique.

A profile's first research pass is an *infant* — it must survive a review/enrichment
gauntlet before it's trusted. The reviewer reads the profile and emits a ReviewReport:
not prose criticism, but a structured set of ReviewFindings, each pointing at a specific
weakness (by claim/thread/source id) and naming the enrichment lane that should fix it.
That makes the later enrichers disciplined (assignments) rather than "go research more".
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field

# What kind of weakness a finding flags.
FindingType = Literal[
    "thin_grounding",        # high-salience claim not backed by a deep-read source
    "overclaim",             # status/salience stronger than the evidence supports
    "missing_primary_source",  # rests on aggregators/secondary; a primary exists
    "missing_perspective",   # one-sided; a serious opposing view is absent
    "generic_thread",        # high-level / says nothing a reader couldn't guess
    "unresolved_causality",  # asserts a cause that isn't established
    "needs_data",            # would be much stronger with analytics (chart/metric/table)
    "weak_context",          # the surrounding field is thin / under-mapped
    "source_concentration",  # too few independent sources / one outlet dominates
    "other",
]
Severity = Literal["low", "medium", "high", "blocking"]
# The reviewer's overall judgment of the profile's maturity.
ReviewVerdict = Literal["mature", "needs_enrichment", "needs_verification", "unsound"]
# Which enrichment lane should act on a finding (an extensible registry).
EnrichmentLane = Literal[
    "primary_source", "counter_perspective", "discussion_landscape",
    "social_x", "analytics", "gap_fill",
]


class ReviewFinding(BaseModel):
    """One targeted weakness + the enrichment that would fix it."""

    id: str
    type: FindingType
    severity: Severity = "medium"
    target: str = "profile"          # claim_id / thread_id / source_id / "profile"
    explanation: str = ""            # what's wrong, specifically
    recommended_enrichment: str = ""  # what to do about it
    suggested_search_direction: str = ""  # a concrete lead for the enricher
    lane: EnrichmentLane | None = None    # which lane should handle it
    maturity_blocker: bool = False   # does this block the profile from being "mature"?


class ReviewReport(BaseModel):
    """The reviewer's verdict + findings — the map of weaknesses the gauntlet works from."""

    id: str
    profile_id: str = ""
    verdict: ReviewVerdict = "needs_enrichment"
    summary: str = ""                # one-paragraph editorial assessment
    findings: list[ReviewFinding] = Field(default_factory=list)
    recommended_lanes: list[EnrichmentLane] = Field(default_factory=list)
    reviewer: str = ""               # agent / version
    model: str = ""
    generated_at: str = ""
