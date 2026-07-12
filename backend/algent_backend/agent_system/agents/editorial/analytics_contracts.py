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
