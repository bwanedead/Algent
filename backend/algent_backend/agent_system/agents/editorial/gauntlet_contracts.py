"""
Planning-gauntlet contract — the report of one bounded plan/review/revise round.

Mirrors the profile gauntlet: a treatment earns promotion by surviving independent review,
not by being produced. v1 is one bounded revision round; a still-`needs_revision` final
verdict is a valid success (the point is to prove the lifecycle, not to force promotion).
"""

from __future__ import annotations

from pydantic import BaseModel, Field

from .review_contracts import TreatmentVerdict


class PlanningGauntletReport(BaseModel):
    """What happened across plan -> review -> (revise -> re-review)."""

    profile_id: str = ""
    treatment_id: str = ""
    starting_revision: int = 1
    ending_revision: int = 1
    revised: bool = False                          # did a revision pass run?
    promoted: bool = False                         # is the final verdict 'promoted'?
    initial_verdict: TreatmentVerdict | str = ""
    final_verdict: TreatmentVerdict | str = ""
    initial_findings: int = 0
    remaining_findings: int = 0
    remaining_blockers: int = 0
    better_frame_offered: str = ""                 # a reviewer's alternate-frame suggestion, if any
    findings_addressed: list[str] = Field(default_factory=list)  # finding ids the revision targeted
    generated_at: str = ""
