"""
Editorial-pipeline contract — the end-to-end report: profile in, finished article out.

Chains the two gauntlets that already work (planning, then drafting) so a single run turns a
research profile into an actual article. Unsound treatments hold before drafting; thin
evidence spines hold at publish even when citations are grounded. This report carries the
quality signals a human approval surface would read.
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
    publishable: bool = False        # status == "publishable"
    # The single honest signal for the human approval surface. v3b (the caveat reviewer) verifies
    # the prose actually keeps its flagged promises; its pass earns "publishable", its fail holds.
    status: str = ""                 # publishable | needs_hedging | blocked | thin_spine | …
    caveat_verdict: str = ""         # v3b: verified | needs_hedging (AFTER any repair lap)
    caveat_findings: int = 0         # how many places the prose failed to hedge (0 = clean)
    # 1 = clean first pass; 2 = the self-heal lap ran (findings -> targeted hedge -> re-check).
    # A run that repeatedly needs the lap is a signal to tune the drafter, not the reviewer.
    caveat_rounds: int = 1
    # Comprehension (gate C) — advisory, NOT a publish gate: a hard-to-follow piece is a dud, not a
    # lie, so it ships either way, but earns one bounded ramp-repair lap first.
    comprehension_verdict: str = ""   # clear | needs_ramp (after any repair lap)
    comprehension_findings: int = 0   # unexplained terms / islands / lost threads still standing
    comprehension_rounds: int = 1
    #: Country flags the comprehension reviewer judged the piece does not earn. Applied by the
    #: publish converter — see ``pipeline._comprehension_pass`` for why the call lives there.
    places_to_drop: list[str] = Field(default_factory=list)
    analytics_warranted: bool = False  # would a chart/table/insight/illustration aid this story?
    analytics_count: int = 0           # grounded analytics requested
    analytics_produced: int = 0        # requests the (gated) worker actually fulfilled into artifacts
    analytics_escapes: int = 0         # worker runs that broke their lane (tripwire) — should stay 0
    #: The hero illustration, when one was generated: artifact_name, alt, hook, label, model,
    #: size, estimated_usd. Absent (None) whenever the stage was off, skipped or failed — the
    #: article is complete either way, so this is never a signal of a broken run.
    hero: dict | None = None
    article_title: str = ""
    word_count: int = 0
    barriers: list[str] = Field(default_factory=list)  # walled sources carried with honest caveats
    unverified_figures: list[str] = Field(default_factory=list)  # prose figures that drifted off the cited evidence
    generated_at: str = ""
