"""
Editorial-pipeline contract — the end-to-end report: profile in, finished article out.

Chains the two gauntlets that already work (planning, then drafting) so a single run turns a
research profile into an actual article. The article is always produced (the best we can do);
this report carries the quality signals a human approval surface would read.
"""

from __future__ import annotations

from pydantic import BaseModel, Field


class EditorialPipelineReport(BaseModel):
    """What the full editorial run produced + how trustworthy it is."""

    profile_id: str = ""
    treatment_id: str = ""
    treatment_verdict: str = ""      # planning gauntlet's final verdict (promoted | needs_revision | …)
    draft_id: str = ""
    draft_outcome: str = ""          # grounded | grounded_with_caveats | blocked_omission
    publishable: bool = False        # the draft cleared the floor (grounded or grounded_with_caveats)
    article_title: str = ""
    word_count: int = 0
    barriers: list[str] = Field(default_factory=list)  # walled sources carried with honest caveats
    generated_at: str = ""
