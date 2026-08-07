"""
Analytics contracts — the request seam between "this story would be clearer with a visual" and the
(sandboxed, later) worker that builds it.

The router ASSESSES a profile and, only where it genuinely aids the reader, emits grounded
AnalyticsRequests — each tied to the profile's real data by id (no invented numbers, no
decoration). A separate grok-build worker fulfills them later; this contract is the hand-off.
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field

# What kind of analytic.
# - chart/table/insight: quantities from real data
# - image: labeled MAP (preferred) or structural diagram via the analytics worker — never a
#   fabricated photo of a real news event. Future: optional theme-illustration (Grok Imagine /
#   similar) may land as a separate honest "AI atmosphere" asset with its own label — not as
#   evidence and not as a stand-in for a map.
AnalyticKind = Literal["chart", "table", "insight", "image"]
RequestStatus = Literal[
    "requested", "produced", "skipped", "failed",
    # Explicit visual-plan outcomes so digests/receipts never imply "forgotten".
    "not_warranted", "soft_cap_skipped", "worker_disabled",
    "source_unavailable", "integrity_check_failed",
]
VisualClass = Literal[
    "locator_map", "data_chart", "comparison", "timeline",
    "process_diagram", "source_specimen", "other",
]
VisualPriority = Literal["essential_context", "high_value", "optional"]
VisualPlacement = Literal["after_quick_take", "after_opening", "after_section", "mid_body"]


class AnalyticsRequest(BaseModel):
    """One useful ask: build this analytic to answer this question for a house reader.

    Profile and analytics are largely separate: the profile need not already hold a time series.
    Prefer ``data_refs`` when claims/sources in the profile already carry the numbers; set
    ``may_source`` + ``source_hint`` when usefulness is clear and public data is likely available
    to fetch at analytics time. Never invent numbers either way.
    """

    id: str
    kind: AnalyticKind
    title: str = ""                                    # a short label for the produced artifact
    question: str = ""                                 # what the reader learns from it
    spec: str = ""                                     # what to build (e.g. "line chart of PCE y/y, 2024-2026")
    data_refs: list[str] = Field(default_factory=list)  # optional profile claim/source/thread ids
    # When True, the worker may fetch public data described by source_hint (profile need not hold it).
    may_source: bool = False
    source_hint: str = ""                              # where/what to fetch (e.g. "WHO weekly Ebola cases DRC")
    rationale: str = ""                                # why it aids understanding (not decoration)
    visual_class: VisualClass = "other"
    priority: VisualPriority = "optional"
    placement: VisualPlacement = "after_opening"
    reader_gap: str = ""   # the mental model the visual supplies that prose alone cannot
    factual_basis: str = ""  # cited data / public reference geometry / sourced media basis
    # Router emits ``requested`` (or ``source_unavailable`` for deferred classes).
    # Never ``produced`` — that status is owned exclusively by the analytics worker.
    status: RequestStatus = "requested"


class AnalyticsPlan(BaseModel):
    """The router's verdict: whether analytics help here, and the grounded requests if so."""

    id: str
    profile_id: str = ""
    warranted: bool = False                            # most stories don't need a chart — that's fine
    requests: list[AnalyticsRequest] = Field(default_factory=list)
    note: str = ""
    generated_at: str = ""
    generator: str = ""
    model: str = ""


# The AI label every produced analytic carries into the publish view — no visual passes as a
# photograph or as anything but a chart drawn from real data (profile-cited and/or sourced).
AI_ANALYTIC_LABEL = "AI-assisted analytic, built only from real cited or sourced data"
AI_ANALYTIC_LABEL_SOURCED = "AI-assisted analytic; series sourced for this figure (not from the profile ledger)"


class AnalyticsArtifact(BaseModel):
    """One fulfilled request — what the (sandboxed) worker produced, plus the harness's checks.

    The worker draws the visual; the HARNESS owns integrity: it copies the artifact out of the
    sandbox, runs the figure check (the visual analog of ``unverified_prose_figures``), and
    stamps provenance (claim ids, as-of, AI label). ``artifact_name``/``data_name`` are names in
    the run's artifact store — the sandbox scratch folder is emptied after.
    """

    request_id: str
    kind: AnalyticKind
    title: str = ""
    # What the reader learns from it (the router's `question`). Carried through so the published
    # figure can SAY what it shows — a table dropped in with no label is a puzzle, not an analytic.
    question: str = ""
    status: RequestStatus = "produced"                 # produced | skipped | failed
    artifact_name: str = ""                            # the chart/table/insight file in the artifact store
    body_md: str = ""                                  # the produced markdown for a table/insight (inlined by the publish view; empty for image kinds)
    data_name: str = ""                                # the backing data.csv in the artifact store
    caption: str = ""                                  # harness-assembled: worker caption + provenance
    data_refs: list[str] = Field(default_factory=list)  # the claim/source/thread ids it was grounded in
    as_of: str = ""                                    # recency horizon of the underlying data
    ai_label: str = AI_ANALYTIC_LABEL
    figure_check: dict = Field(default_factory=dict)   # {checked, verified, unverified:[...]} — visual drift catch
    #: Data the worker SOURCED that the profile did not already hold, as claim-shaped rows
    #: ``{"text": ..., "url": ...}``.
    #:
    #: Analytics is a research act, not a decoration step. When a figure legitimately fetches
    #: public data — a decade of export totals the profile never gathered — that data is
    #: evidence, and throwing it away the moment the chart is drawn is the waste this field
    #: exists to stop. It flows back into the claim ledger, so the numbers under a figure are
    #: as inspectable as any other claim and the next stage can use them in prose.
    sourced_claims: list[dict] = Field(default_factory=list)
    swept: list[str] = Field(default_factory=list)     # files removed by the artifact-type/size sweep
    escaped_writes: list[str] = Field(default_factory=list)  # repo paths the worker touched OUTSIDE its lane (a hard fail)
    visual_class: VisualClass = "other"
    priority: VisualPriority = "optional"
    placement: VisualPlacement = "after_opening"
    reader_gap: str = ""
    note: str = ""
    generated_at: str = ""
    model: str = ""              # the harness + its exact version (provenance: which tool drew this)
    generator: str = ""
