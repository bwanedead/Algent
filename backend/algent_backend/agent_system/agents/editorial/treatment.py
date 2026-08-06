"""
Editorial contracts — the **EditorialTreatment**: the pre-draft reality-compression.

The article pipeline does not go profile -> prose in one shot. Between the researched
profile and any drafting sits a planning stage whose product is a *treatment*: the
**durable understanding** the drafter inherits, so it does not rediscover the profile from
scratch. The treatment is NOT an outline (no "part 1, part 2") — it is the governing
decision set:

- the **chosen frame** (the reality-revealing vantage) and the **rejected** alternatives;
- the **core understanding** — the concept-molecule the reader should hold at the end;
- the **load-bearing concepts**, their dependencies (chains/towers) and grounding (by id);
- the **perspective map** (every serious side, steelmanned, with evidence);
- the **deception risks** of this particular story, and the **must-use** profile items.

The model authors concept/perspective ids LOCALLY (k1, p1…); the harness validates every
reference against the profile and drops dangling ones (see ``loop.py``). Pure contract —
no storage or rail imports; round-trips to JSON.
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field

SCHEMA_VERSION = 1

CausalStatus = Literal["established", "supported", "possible", "unknown"]


class CausalLink(BaseModel):
    """One explicit cause→effect relation the reader must not have to invent.

    Status is honesty about the evidence, not hedging theater: ``established`` only when the
    profile actually settles it; ``unknown`` when the piece must say the link is open.
    """

    cause: str = ""
    effect: str = ""
    status: CausalStatus = "possible"
    note: str = ""


class FrameOption(BaseModel):
    """A candidate vantage on the story. A value object (no id) — frames are described,
    not addressed; the chosen one governs, the rejected ones show the search was real."""

    frame: str = ""        # one-line description of the lens/vantage
    rationale: str = ""    # why it reveals (chosen) — or why it distorts/obscures (rejected)


class TreatmentConcept(BaseModel):
    """A load-bearing concept the reader must build — a node in the molecule.

    ``id`` is a LOCAL id the model authors (k1, k2…); the harness keeps it stable and
    validates ``depends_on`` against the other concepts and ``grounds_in`` against the
    profile's item ids.
    """

    id: str
    name: str                                          # the understanding the reader must acquire
    why_load_bearing: str = ""                         # the wrong shape that results if it is missing
    depends_on: list[str] = Field(default_factory=list)  # other concept ids (chains/towers)
    grounds_in: list[str] = Field(default_factory=list)  # profile claim/thread/source ids
    resolution: str = ""                               # the grain note (how fine/coarse, and why)
    do_not_overstate: str = ""                         # the ceiling: what may NOT be asserted beyond the grounding


class PerspectiveTake(BaseModel):
    """One serious perspective, rendered at its strongest good-faith form, with evidence."""

    id: str
    label: str                                         # whose view / what stance
    steelman: str = ""                                 # the strongest honest form of this perspective
    grounds_in: list[str] = Field(default_factory=list)  # profile claim/thread/source ids


class Primitive(BaseModel):
    """A textbook concept the reader must already hold to build the molecule — the ramp.

    NOT a claim about the world and NOT news: it is uncontroversial background (what a term is,
    what a mechanism does) the drafter may speak in its own voice, without citation. It lives here,
    on the treatment, precisely because it is not evidence — sourcing textbook knowledge would
    recreate the inventory disease with receipts attached. Anything contested, story-specific, or
    load-bearing for the news itself is NOT a primitive; it is evidence and stays on the profile's
    spine.
    """

    term: str
    plain_meaning: str = ""                            # one plain-language clause a general reader can hold


class EditorialTreatment(BaseModel):
    """The pre-draft reality-compression — the durable understanding the drafter inherits.

    Carries the framing decision, the reader-molecule, the perspective map, the deception
    risks, and the must-use evidence. Rich enough that the drafter writes from it and the
    treatment reviewer can challenge it — without redoing the profile digestion.
    """

    id: str
    profile_id: str = ""
    title: str = ""

    # ── framing (the governing vantage) ──
    chosen_frame: FrameOption = Field(default_factory=FrameOption)
    rejected_frames: list[FrameOption] = Field(default_factory=list)

    # ── the reader-molecule (the reality-shape to convey) ──
    core_understanding: str = ""                       # the molecule the reader should end holding (1-2 sentences)
    # The reader-facing dual of core_understanding: the question, in the reader's words, that this
    # piece answers. The shape is what they hold; this is why they wanted it. Every concept either
    # serves answering it or does not belong — and a vector that can't state one isn't a story.
    reader_question: str = ""
    # Cold-reader ENTRY fields — the first-screen bargain before landscape/methodology.
    # Distinct from core_understanding (end-state molecule) and reader_question (why they came).
    news_kernel: str = ""        # one plain sentence: what concretely happened / was found
    reader_payoff: str = ""      # why a non-specialist should care (usable so-what / reduction)
    key_uncertainty: str = ""    # the most important open, contested, or unresolved link
    # Plain-language subject for specialist topics ("an undeciphered Bronze Age script", not
    # just the guild name). Empty when the subject is already house-readable.
    plain_subject: str = ""
    causal_chain: list[CausalLink] = Field(default_factory=list)
    concepts: list[TreatmentConcept] = Field(default_factory=list)
    reader_path: list[str] = Field(default_factory=list)  # suggested concept-id order (dependency order, NOT prose sections)
    # The ramp: textbook primitives a cold house reader must hold to build the molecule
    # (usually 2–4; up to ~6 for multi-party mechanisms). Drafter voice, not evidence.
    primitives: list[Primitive] = Field(default_factory=list)

    # ── completeness / honesty ──
    perspectives: list[PerspectiveTake] = Field(default_factory=list)
    deception_risks: list[str] = Field(default_factory=list)   # how THIS story could mislead while saying true things
    must_use_items: list[str] = Field(default_factory=list)    # profile item ids the draft must carry (load-bearing)
    open_questions: list[str] = Field(default_factory=list)    # what stays genuinely unknown / to flag as uncertain

    # ── meta / lineage ──
    schema_version: int = SCHEMA_VERSION
    revision: int = 1                                  # bumps each gauntlet revision
    generated_at: str = ""
    generator: str = ""                                # agent id / version
    model: str = ""                                    # model that produced it
