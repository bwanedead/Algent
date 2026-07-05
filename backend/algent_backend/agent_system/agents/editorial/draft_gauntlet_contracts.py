"""
Drafting-gauntlet contract — the report of a draft/audit/revise loop.

v3a is the DETERMINISTIC gate: the drafting gauntlet turns the citation harness's verdict into
a forced revision loop, with ZERO judgment tokens (the gate is pure code; only the drafter,
which must research anyway, re-runs). A draft earns "grounded" the way a profile earns
maturity — by clearing the floor, not by being produced. The semantic multi-lens reviewer is a
later layer (v3b) that bolts onto this working gate. A draft that stays `needs_deep_read` after
the bounded rounds is a valid, honest outcome (some sources genuinely can't be deep-read).
"""

from __future__ import annotations

from pydantic import BaseModel, Field

from .citations import CitationVerdict


class DraftingGauntletReport(BaseModel):
    """What happened across draft -> audit -> (revise -> re-audit)*."""

    treatment_id: str = ""
    profile_id: str = ""
    draft_id: str = ""
    rounds: int = 0                                # drafter passes (1 = no revision)
    promoted: bool = False                         # final verdict == grounded

    initial_verdict: CitationVerdict | str = ""
    final_verdict: CitationVerdict | str = ""
    initial_weak_claims: int = 0
    final_weak_claims: int = 0
    final_must_use_missing: int = 0
    final_worklist: list[str] = Field(default_factory=list)  # sources still needing a deep read, if any
    ending_profile_revision: int = 1               # enrich-back bumps this as reads land
    generated_at: str = ""
