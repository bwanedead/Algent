"""
Comprehension-check contracts — the naive-reader lane (gate C).

Every other gate reads the piece from OUR side: does the prose keep its evidentiary promises, do
the figures match the ledger, was the counter-position carried. None of them can see the one thing
that only exists on the READER's side — did the shape actually transfer. Comprehension failure is
invisible by construction to any stage that knows what the piece is trying to say; you have to not
know, and read it cold.

So this reviewer reads ONLY the prose — no profile, no treatment, no evidence — as a
decently-informed generalist, and reports where the ramp is missing or the molecule arrives without
its bonds. Its power is deliberately one-sided and symmetric with the rest of the system: it may
demand a HANDHOLD or a CUT, never "assert this harder" and never "add more everywhere". It flags
where understanding breaks; it cannot manufacture confidence.
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field

ComprehensionVerdict = Literal["clear", "needs_ramp"]


class ComprehensionFinding(BaseModel):
    """One place a decently-informed reader loses the thread or hits a wall with no handhold."""

    id: str
    kind: Literal[
        "unexplained_term",    # term/acronym/measure left cold (name alone may still fail)
        "unknown_actor",       # person/org/body without what-it-is / what-it-does-here handhold
        "missing_scene",       # country/system/scheme never oriented before chronology or stakes
        "assumed_context",     # a sentence that only parses if you already know something unavailable
        "island_paragraph",    # a block with no relation to the through-line — a node with no edges
        "lost_thread",         # the point where the piece stopped being followable
        "unconnected_inference",  # conclusion dropped without the premise that makes it land
        "no_reduction",        # finished piece with no holdable so-what for a house reader
        "one_sided_picture",   # contested topic; only one serious public case is visible
        "other",
    ] = "other"
    where: str = ""            # a short quote / locator so the fix is targeted, not a rewrite
    issue: str = ""            # what breaks for the reader here
    # The fix is constrained to HANDHOLD-or-CUT — a one-clause plain-language ramp, a real transition
    # onto the through-line, or removal. NEVER "assert more" or "add detail everywhere".
    fix: Literal["add_handhold", "connect_to_thread", "cut"] = "add_handhold"
    suggestion: str = ""       # the specific handhold/transition to add, or what to cut


class ComprehensionCheck(BaseModel):
    """The verdict on whether the shape actually transfers to a general reader."""

    id: str
    draft_id: str = ""
    verdict: ComprehensionVerdict = "clear"
    summary: str = ""          # one line: did it land, and if not, the biggest break
    findings: list[ComprehensionFinding] = Field(default_factory=list)
    reviewer: str = ""
    model: str = ""
    generated_at: str = ""
