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

from pydantic import BaseModel, Field

SCHEMA_VERSION = 1


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
    concepts: list[TreatmentConcept] = Field(default_factory=list)
    reader_path: list[str] = Field(default_factory=list)  # suggested concept-id order (dependency order, NOT prose sections)

    # ── completeness / honesty ──
    perspectives: list[PerspectiveTake] = Field(default_factory=list)
    deception_risks: list[str] = Field(default_factory=list)   # how THIS story could mislead while saying true things
    must_use_items: list[str] = Field(default_factory=list)    # profile item ids the draft must carry (load-bearing)
    open_questions: list[str] = Field(default_factory=list)    # what stays genuinely unknown / to flag as uncertain

    # ── meta ──
    schema_version: int = SCHEMA_VERSION
    generated_at: str = ""
    generator: str = ""                                # agent id / version
    model: str = ""                                    # model that produced it
