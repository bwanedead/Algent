"""
Confirmation of claims the analytics worker contributed to the ledger.

The worker may add evidence — a figure that legitimately fetches a decade of export totals is
doing research, and throwing that away when the chart is drawn is waste. What it may NOT do is
grade its own work. It is a sandboxed coding harness whose file output we already integrity-check
before trusting; asking the same pass that fetched a number to also certify it is self-attestation,
and a ledger that recorded that as ``confirmed`` would be lying about where its confidence came
from.

So worker-contributed claims land as ``unconfirmed`` and a separate research pass — its own model,
its own searches, its own sources — decides. That is the same independence the rest of the ledger
already assumes: nothing here is confirmed by the actor that produced it.
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field

#: What the confirming pass concluded about one worker-contributed claim.
#:
#: - ``confirmed``   — an independent source says the same thing.
#: - ``contested``   — an independent source materially disagrees. The FIGURE built on it is
#:                     suspect, not just the ledger row, so this is reported loudly.
#: - ``unconfirmed`` — could not verify either way. Honest and common; the claim stays as it
#:                     arrived rather than being quietly upgraded or deleted.
ClaimVerdict = Literal["confirmed", "contested", "unconfirmed"]


class ClaimCheck(BaseModel):
    """One claim, checked against sources the analytics worker did not choose."""

    claim_id: str
    verdict: ClaimVerdict = "unconfirmed"
    #: Why — in plain words, naming what the independent source actually said. For ``contested``
    #: this must state the disagreement concretely (the other figure, the other date), because a
    #: bare "does not match" tells the next stage nothing about whether the chart can be salvaged.
    reason: str = ""
    #: URLs consulted for THIS claim. Empty on ``unconfirmed`` means nothing was found; empty on
    #: ``confirmed`` is a contradiction and the harness refuses the upgrade.
    checked_against: list[str] = Field(default_factory=list)
    #: The value the independent source gave, when it differs. Feeds figure repair.
    source_value: str = ""


class AnalyticsConfirmReport(BaseModel):
    """The pass's verdict over every claim analytics contributed."""

    profile_id: str = ""
    checks: list[ClaimCheck] = Field(default_factory=list)
    note: str = ""
    generated_at: str = ""
    generator: str = ""
    model: str = ""

    def counts(self) -> dict[str, int]:
        out = {"confirmed": 0, "contested": 0, "unconfirmed": 0}
        for c in self.checks:
            out[c.verdict] = out.get(c.verdict, 0) + 1
        return out
