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
        "vague_conflict",      # cannot state what the dispute is about / who wants what / why
        "announced_importance",  # machine signature: labels significance instead of showing it
        # Written from OUR vantage point, not the reader's: "the case" / "the claim" on first use,
        # a before/after only we can see, a figure or catalogue number the reader cannot see, our
        # research pass as the subject ("this pass", "cannot be verified here"). The reader has
        # read nothing but this piece. See style.md machine signature 4 — this is the most common
        # defect and the hardest to see from inside the pipeline, which is why it is named here.
        "drafter_vantage",
        "island_paragraph",    # a block with no relation to the through-line — a node with no edges
        "lost_thread",         # the point where the piece stopped being followable
        "unconnected_inference",  # conclusion dropped without the premise that makes it land
        "no_reduction",        # finished piece with no holdable so-what for a house reader
        "one_sided_picture",   # contested topic; only one serious public case is visible
        "other",
    ] = "other"
    where: str = ""            # a short quote / locator so the fix is targeted, not a rewrite
    issue: str = ""            # what breaks for the reader here
    # Mostly HANDHOLD-or-CUT — a one-clause plain-language ramp, a real transition onto the
    # through-line, or removal. NEVER "assert more" or "add detail everywhere".
    #
    # ``rewrite_for_reader`` exists because handhold-or-cut cannot repair the most common defect
    # we ship. A sentence written from our vantage — an opening that rebuts a source the reader
    # never saw, a paragraph that justifies why an item is in the piece, our own research state
    # narrated as prose — is not missing a handhold and is not merely cuttable: the information
    # is wanted, the framing is wrong. It has to be said again from the reader's side, with the
    # same facts. Without this option the reviewer could only ask for a ramp onto a sentence
    # that should not have been phrased that way, which is why two repair laps changed nothing.
    fix: Literal["add_handhold", "connect_to_thread", "cut", "rewrite_for_reader"] = "add_handhold"
    suggestion: str = ""       # the handhold/transition to add, what to cut, or the reader-side rewrite


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
