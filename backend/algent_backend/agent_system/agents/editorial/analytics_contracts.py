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

# What kind of analytic. `image` is an AI-generated ILLUSTRATION (diagram/concept art), never a
# fabricated photo of a real event — see the worker doctrine.
AnalyticKind = Literal["chart", "table", "insight", "image"]
RequestStatus = Literal["requested", "produced", "skipped", "failed"]


class AnalyticsRequest(BaseModel):
    """One grounded ask: build this analytic from this data, to answer this question."""

    id: str
    kind: AnalyticKind
    title: str = ""                                    # a short label for the produced artifact
    question: str = ""                                 # what the reader learns from it
    spec: str = ""                                     # what to build (e.g. "line chart of PCE y/y, 2024-2026")
    data_refs: list[str] = Field(default_factory=list)  # profile claim/source/thread ids that supply the data
    rationale: str = ""                                # why it aids understanding (not decoration)
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
# photograph or as anything but a chart drawn from the cited data.
AI_ANALYTIC_LABEL = "AI-assisted analytic, built only from cited data"


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
    status: RequestStatus = "produced"                 # produced | skipped | failed
    artifact_name: str = ""                            # the chart/table/insight file in the artifact store
    body_md: str = ""                                  # the produced markdown for a table/insight (inlined by the publish view; empty for image kinds)
    data_name: str = ""                                # the backing data.csv in the artifact store
    caption: str = ""                                  # harness-assembled: worker caption + provenance
    data_refs: list[str] = Field(default_factory=list)  # the claim/source/thread ids it was grounded in
    as_of: str = ""                                    # recency horizon of the underlying data
    ai_label: str = AI_ANALYTIC_LABEL
    figure_check: dict = Field(default_factory=dict)   # {checked, verified, unverified:[...]} — visual drift catch
    swept: list[str] = Field(default_factory=list)     # files removed by the artifact-type/size sweep
    escaped_writes: list[str] = Field(default_factory=list)  # repo paths the worker touched OUTSIDE its lane (a hard fail)
    note: str = ""
    generated_at: str = ""
    model: str = ""              # the harness + its exact version (provenance: which tool drew this)
    generator: str = ""
