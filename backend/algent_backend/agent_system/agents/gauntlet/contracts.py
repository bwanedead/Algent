"""
Gauntlet contracts — the orchestrator's summary of one review/enrichment round.

The gauntlet runs review -> enrich (per lane) -> merge -> re-review as one bounded
lifecycle. This report records what happened: where the profile started, what lanes ran,
what they addressed, where it ended, and whether the re-review thinks it's better.
"""

from __future__ import annotations

from pydantic import BaseModel, Field


class GauntletReport(BaseModel):
    """The outcome of one bounded gauntlet round."""

    profile_id: str = ""
    rounds: int = 1
    starting_revision: int = 1
    ending_revision: int = 1
    lanes_run: list[str] = Field(default_factory=list)
    #: Findings the lanes were sent to work on. NOT a claim that they were resolved —
    #: review ids are renumbered per review, so resolution cannot be read off an id
    #: diff. `remaining_findings` is the honest count of what is still open.
    findings_attempted: list[str] = Field(default_factory=list)
    initial_verdict: str = ""
    final_verdict: str = ""
    initial_findings: int = 0
    remaining_findings: int = 0
    remaining_blockers: int = 0
    generated_at: str = ""
