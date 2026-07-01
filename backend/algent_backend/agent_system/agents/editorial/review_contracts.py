"""
Treatment-review contracts — the fresh-eyes critique of an EditorialTreatment.

A treatment is the highest-leverage editorial decision (the frame + the molecule), so it
earns promotion the same way a profile does: by surviving an independent review. The
treatment reviewer is NOT the planner grading itself — it is a separate vantage that asks
the questions a planner is biased against asking about its own frame:

    "Is this the most reality-revealing vantage, or just the first good one?"
    "What would the reader falsely believe after receiving this molecule?"
    "Which load-bearing branch — concept or serious perspective — is missing?"
    "Is a perspective flattened, or scrutiny applied asymmetrically?"
    "Does any concept assert beyond its grounding (certainty laundering)?"
    "Is the molecule quietly steering toward a conclusion?"

It emits a TreatmentReview: targeted findings (each pointing at a frame/concept/perspective)
+ a verdict. Pure contract — no rail imports.
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field

# What kind of weakness a finding flags.
TreatmentFindingType = Literal[
    "frame_challenge",      # a more reality-revealing vantage exists, or the frame distorts/flatters/steers
    "missing_branch",       # a load-bearing concept or serious perspective is absent (omission)
    "false_symmetry",       # perspectives equalized when evidence is asymmetric, or asymmetric scrutiny
    "certainty_laundering", # a concept asserts more than its grounding supports (weak do_not_overstate)
    "thin_grounding",       # a concept/perspective not grounded in profile items
    "steering",             # the molecule installs an unwarranted conclusion (capture)
    "weak_core",            # the core_understanding does not capture the real shape
    "other",
]
Severity = Literal["low", "medium", "high", "blocking"]
# The reviewer's overall judgment of the treatment.
TreatmentVerdict = Literal["promoted", "needs_revision", "unsound"]


class TreatmentFinding(BaseModel):
    """One targeted weakness in the treatment + how to fix it."""

    id: str
    type: TreatmentFindingType
    severity: Severity = "medium"
    target: str = "treatment"      # "frame" | "core" | a concept id | a perspective id | "treatment"
    explanation: str = ""          # what's wrong, specifically
    recommendation: str = ""       # what the revision should do about it
    promotion_blocker: bool = False  # does this block the treatment from being promoted?


class TreatmentReview(BaseModel):
    """The reviewer's verdict + findings — the map the revision works from."""

    id: str
    treatment_id: str = ""
    profile_id: str = ""
    verdict: TreatmentVerdict = "needs_revision"
    summary: str = ""              # one-paragraph editorial assessment
    findings: list[TreatmentFinding] = Field(default_factory=list)
    better_frame: str = ""         # if a more revealing vantage exists, name it (else empty)
    reviewer: str = ""             # agent / version
    model: str = ""
    generated_at: str = ""
