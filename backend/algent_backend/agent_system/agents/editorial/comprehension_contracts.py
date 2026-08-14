"""
Comprehension-check contracts — the naive-reader lane (gate C).

Every other gate reads the piece from OUR side: does the prose keep its evidentiary promises, do
the figures match the ledger, was the counter-position carried. None of them can see the one thing
that only exists on the READER's side — did the shape actually transfer. Comprehension failure is
invisible by construction to any stage that knows what the piece is trying to say; you have to not
know, and read it cold.

So this reviewer reads ONLY the prose — no profile, no treatment, no evidence — as a
decently-informed generalist. When the shape does not transfer, it emits the next draft itself
from what is already on the page. It does not telephone findings back to the drafter. Its power
is still one-sided: it may clarify, cut, reorder, and restate from the reader's side — never
"assert this harder" and never invent. Findings are the audit of what was wrong; the rewrite is
the repair.
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
        # A country flag beside the headline that the piece never justifies. Flags are the
        # reader's first orientation cue, so an unexplained one is a question the article
        # raises and never answers: a shipped Swift piece flew a South Africa flag with no
        # mention of the country anywhere in the prose. Two honest repairs exist and the
        # reviewer picks — say why the country is in the story, or take the flag off.
        "unjustified_flag",
        # -- polish and production value ------------------------------------------------
        # A piece assembled from a claim ledger reads like one: true sentences in the order
        # the evidence arrived rather than the order an idea unfolds. These name the seams.
        "buried_point",        # the thing that makes the story interesting arrives too late
        "rough_seam",          # unheralded jump, register change, or source-ordered structure
        "repetition",          # a point argued twice; one statement is the budget
        "wire_echo",           # reads as a restatement of one outlet's framing and sequence
        "causal_gap",          # the mechanism is left to be deduced instead of stated
        "unearned_figure",     # a chart that answers no question, or is not legible at a glance
        "garbled_detail",      # a mangled proper noun or a number that disagrees with itself
        "island_paragraph",    # a block with no relation to the through-line — a node with no edges
        "lost_thread",         # the point where the piece stopped being followable
        "unconnected_inference",  # conclusion dropped without the premise that makes it land
        "no_reduction",        # finished piece with no holdable so-what for a house reader
        "one_sided_picture",   # contested topic; only one serious public case is visible
        # -- reader-entry / information hierarchy -----------------------------------------
        # Openings that bury the news behind orientation, or lead with guild names before
        # meaning, or dump methodology before the payoff. Soft promotion still ships; these
        # name the repair.
        "missing_news_kernel",  # first screen never states what happened / was found
        "opening_order",        # landscape / etymology / methodology before the event
        "jargon_before_gloss",  # specialist name or initialism before plain meaning
        "unclear_causal_chain", # policy→event or mechanism link left foggy or overstated
        "method_before_payoff", # technical how-to arrives before the reader holds the finding
        "lecture",              # apparatus taught past the grain needed for significance
        "wall_of_text",         # long uninterrupted prose with no headings / figures / breaks
        "other",
    ] = "other"
    where: str = ""            # locator on the prior draft — audit trail, not a patch instruction
    issue: str = ""            # what broke for the reader here
    # Kind of change made in the rewrite (or why the page could not support one).
    # Never "assert more" or "add detail everywhere".
    fix: Literal[
        "add_handhold", "connect_to_thread", "cut", "rewrite_for_reader", "reorder",
    ] = "add_handhold"
    suggestion: str = ""       # what you changed in the rewrite (or why you could not, from the page)


class ComprehensionCheck(BaseModel):
    """The verdict on whether the shape actually transfers to a general reader.

    When ``verdict`` is ``needs_ramp``, ``title`` / ``standfirst`` / ``body`` ARE the next draft —
    written from the page, not instructions for the article drafter. Empty when ``clear``.
    """

    id: str
    draft_id: str = ""
    verdict: ComprehensionVerdict = "clear"
    summary: str = ""          # one line: did it land, and if not, the biggest break
    findings: list[ComprehensionFinding] = Field(default_factory=list)
    title: str = ""            # next draft title when needs_ramp; empty when clear
    standfirst: str = ""
    body: str = ""             # next draft body when needs_ramp; empty when clear
    #: Country flags this reviewer judges the piece does not earn, by display name.
    #: The reviewer is the right place for this call: flags are assigned from the profile's
    #: declared geography, which is decided before anyone has read the finished prose, so
    #: nothing upstream can know whether the article actually accounts for a country. Dropping
    #: a flag is the alternative to earning it in the rewrite — see ``unjustified_flag``.
    places_to_drop: list[str] = Field(default_factory=list)
    reviewer: str = ""
    model: str = ""
    generated_at: str = ""
