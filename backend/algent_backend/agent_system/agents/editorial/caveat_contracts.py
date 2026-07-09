"""
Caveat-check contracts — v3b's first (and only, for now) semantic lane.

The harness deterministically PROVES the walls, the overstatements-at-risk, and the drifted
figures; what it can't check is whether the PROSE actually keeps the promise — hedges the walled
source, states the contested claim at its grade, dates the volatile figure. That is the last
promise standing on doctrine rather than a floor. This reviewer closes it: a cheap LLM judge that
reads ONLY the pre-computed flagged items against the prose and confirms each is honestly handled.
Its pass is what flips ``publishable_pending_caveat_check`` to a verified ``publishable``.
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field

CaveatVerdict = Literal["verified", "needs_hedging"]


class CaveatFinding(BaseModel):
    """One place the prose asserts more than its evidence allows."""

    id: str
    target: str = ""     # the claim id / figure / source the prose mishandles
    kind: Literal["overstatement", "unhedged_source", "bare_figure", "other"] = "other"
    issue: str = ""      # what the prose does that exceeds the evidence
    fix: str = ""        # what it should say instead


class CaveatCheck(BaseModel):
    """The verdict on whether the prose keeps every flagged promise."""

    id: str
    draft_id: str = ""
    verdict: CaveatVerdict = "verified"
    summary: str = ""
    findings: list[CaveatFinding] = Field(default_factory=list)
    reviewer: str = ""
    model: str = ""
    generated_at: str = ""
