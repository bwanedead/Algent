"""
Pulse contracts — Ohmega's persistent, auditable belief states.

A **Situation** is an enduring real-world subject (Russia–NATO). A **Pulse** is one assessed
dimension of it (military confrontation), measured against a versioned ruler of **anchors**.
Every time anything touches a Pulse, an immutable **Influence** is appended; the Pulse's current
state is a projection of that log (``projection.py``), never an overwritten number.

Three kinds of change are kept apart, because they answer different questions:
- an influence  — evidence was considered (including "no material change");
- a value move  — the internal position moved (61 → 66): what velocity and sparklines are made of;
- a band change — the public category crossed a threshold (Elevated → Severe): the publishable subset.

Design rules this file encodes (docs/architecture/pulse-system.md):
- assessments PROPOSE A POSITION against the anchors, never a delta — each is a fresh estimate
  on a stable ruler, so repeated news cannot ratchet the value;
- every influence records the definition version it was made under, so history stays comparable
  after the ruler is improved;
- confidence keeps its reasons (quality / coverage / agreement / freshness);
- an influence's key makes a retried run unable to write the same history twice.
"""

from __future__ import annotations

import hashlib
from typing import Literal

from pydantic import BaseModel, Field

#: Public bands, keyed by the lower edge of the 0–100 position. The anchors give the numbers
#: their meaning; the bands are only how the position is shown to a reader.
BANDS: tuple[tuple[float, str], ...] = (
    (0.0, "calm"), (25.0, "elevated"), (50.0, "severe"), (75.0, "critical"),
)

Mode = Literal["seed", "article", "reassess", "blind"]
Decision = Literal["applied", "no_change", "rejected", "reconcile"]


def band_of(position: float) -> str:
    name = BANDS[0][1]
    for edge, label in BANDS:
        if position >= edge:
            name = label
    return name


class Anchor(BaseModel):
    """One point on a Pulse's ruler: what this position MEANS, with a real example."""

    position: float                      # 0, 25, 50, 75, 100
    meaning: str
    example: str = ""                    # a historical moment that sat here


class PulseDefinition(BaseModel):
    """What a Pulse measures — a loose FRAME, not a fixed ruler. Versioned; never edited in place.

    Only the direction and the two ends are fixed: 0 is the calm end, 100 the extreme end. Between
    them there are no pre-drawn boxes. A Pulse's scale is its own HISTORY: every reading is placed
    by comparing today's evidence with the evidence behind its past readings ("worse than when we
    said 58 on Aug 14, because…"). The scale grows from experience and bends with the world, and it
    stays comparable because each reading is argued against the ones before it (operator, 09-30:
    fixed anchors "box it in"; let it breathe the way the world actually is).

    ``anchors`` survives only for Pulses seeded under the earlier fixed-ruler doctrine.
    """

    version: int = 1
    question: str                        # the plain-words question this Pulse answers
    low_end: str = ""                    # what 0 looks like — the calm, normal end
    high_end: str = ""                   # what 100 looks like — the extreme end of this dimension
    anchors: list[Anchor] = Field(default_factory=list)   # legacy (fixed-ruler doctrine)
    created_at: str = ""
    note: str = ""                       # why this version exists (what changed)


class Pulse(BaseModel):
    id: str                              # pls_russia_nato_military
    situation_id: str
    name: str                            # "Military confrontation"
    status: Literal["experimental", "active", "dormant"] = "experimental"
    definitions: list[PulseDefinition] = Field(default_factory=list)   # every version, oldest first

    @property
    def definition(self) -> PulseDefinition:
        return self.definitions[-1]


class Situation(BaseModel):
    id: str                              # sit_russia_nato
    domain: str = "geopolitics"          # domain-agnostic by design (sports can plug in)
    title: str
    summary: str = ""
    entities: list[str] = Field(default_factory=list)   # canonical names / aliases it covers
    pulse_ids: list[str] = Field(default_factory=list)
    parent_id: str = ""                  # set when split from a broader situation
    status: Literal["active", "dormant", "merged"] = "active"
    created_at: str = ""


class Confidence(BaseModel):
    """Why we are as sure as we are. Compressed to high/medium/low only for display."""

    evidence_quality: Literal["high", "medium", "low"] = "medium"
    coverage: Literal["high", "medium", "low"] = "medium"
    agreement: Literal["high", "medium", "low", "unknown"] = "unknown"   # vs independent reads
    note: str = ""

    def overall(self) -> str:
        levels = [self.evidence_quality, self.coverage]
        if self.agreement != "unknown":
            levels.append(self.agreement)
        if "low" in levels:
            return "low"
        return "high" if all(v == "high" for v in levels) else "medium"


class Source(BaseModel):
    """What produced an influence — the trace back to the research that justified it."""

    run_id: str = ""
    stage: str = ""                      # which part of the machine (rail editorial, reassess…)
    profile_id: str = ""
    article_slug: str = ""
    claim_ids: list[str] = Field(default_factory=list)
    event_id: str = ""


class Influence(BaseModel):
    """One immutable log entry: something touched this Pulse. Appended, never edited."""

    key: str = ""                        # idempotency — see influence_key()
    pulse_id: str
    at: str                              # when it was assessed (ISO)
    evidence_through: str = ""           # latest evidence date this assessment saw
    mode: Mode
    definition_version: int
    proposed_position: float | None = None   # None = considered, no position taken
    decision: Decision
    rationale: str
    confidence: Confidence = Field(default_factory=Confidence)
    source: Source = Field(default_factory=Source)
    prompt_version: str = ""
    model: str = ""
    watch_ids_triggered: list[str] = Field(default_factory=list)


def influence_key(pulse_id: str, event_id: str, run_id: str, mode: str) -> str:
    """Stable identity of one assessment act. A retry of the same run cannot append it twice."""
    raw = "|".join((pulse_id, event_id or "-", run_id or "-", mode))
    return "inf_" + hashlib.sha1(raw.encode("utf-8")).hexdigest()[:16]


class Event(BaseModel):
    """A real-world occurrence the research was about. Because assessments are POSITIONS, a
    second article on the same event re-estimates rather than double-counts; the event record is
    what lets the timeline show one incident once."""

    id: str
    summary: str
    occurred_on: str = ""                # YYYY-MM-DD when known
    place: str = ""
    situation_ids: list[str] = Field(default_factory=list)
    sources: list[Source] = Field(default_factory=list)


def event_id(summary: str, occurred_on: str) -> str:
    norm = " ".join(summary.lower().split())
    return "evt_" + hashlib.sha1(f"{occurred_on}|{norm}".encode("utf-8")).hexdigest()[:12]


class Watch(BaseModel):
    """A forward condition. Triggered/expired watches are the calibration dataset."""

    id: str
    situation_id: str
    condition: str
    why: str = ""
    evidence_needed: str = ""
    pulse_ids: list[str] = Field(default_factory=list)
    expected_direction: Literal["up", "down", "either"] = "either"
    horizon: str = ""                    # ISO date or "" when open-ended
    origin_positions: dict[str, float] = Field(default_factory=dict)   # Pulse states when created
    status: Literal["open", "triggered", "expired", "invalidated"] = "open"
    created_at: str = ""
    resolved_at: str = ""
    resolved_by: Source | None = None
