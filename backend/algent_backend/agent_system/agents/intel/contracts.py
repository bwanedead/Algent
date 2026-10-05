"""
Intel contracts — the watch recipe: emergent theaters, their heat, and the intelligence brief.

A **theater** is not configured. It is a grouping the heat detector finds in what is actually being
reported — "Russia's sabotage campaign against European logistics" — and it earns its place by
persisting. Theaters that last become Pulse situations; theaters that cool fade. Nothing here names
a country or a conflict: the same recipe runs on any domain's feed (``domain`` is data).

A **brief** is intelligence, not an article: a bottom line, a dated timeline where every item says
how far it is verified, the direction and pace of escalation, who is doing what to whom, the
second-order effects and peripheral things to watch, indicators and warnings, and what we do not
know. Facts and assessments are kept apart, the way an analyst's product must.
"""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field, field_validator

Verification = Literal["researched", "reported"]   # graded by our research / headline only


class Member(BaseModel):
    """One headline that belongs to a theater."""

    edition: str                     # radar edition slug (YYYY-MM-DD-HHMM); other classes: YYYY-MM-DD-<class>
    n: int                           # its number in that edition
    kind: str = "radar"              # source class: radar | wikipedia | library (see ``base``)
    title: str
    thesis: str = ""
    sources: list[str] = Field(default_factory=list)


class Theater(BaseModel):
    id: str                          # thr_<slug>
    name: str
    domain: str = "geopolitics"
    description: str = ""
    why: str = ""                    # why these belong together (the dynamic, not the keyword)
    members: list[Member] = Field(default_factory=list)
    situation_id: str = ""           # the Pulse situation it maps to, when one exists


class HeatPoint(BaseModel):
    day: str
    count: int                       # the theater's headlines that day (raw)
    editions: int = 0                # radar editions built that day — 0 is a coverage gap, not a quiet day


class ClassShare(BaseModel):
    """One source class's view of a theater: its members and the class's headlines in each window."""

    recent: int = 0
    recent_n: int = 0
    prior: int = 0
    prior_n: int = 0


class TheaterHeat(BaseModel):
    theater_id: str
    name: str
    series: list[HeatPoint] = Field(default_factory=list)   # headlines per day, oldest first
    total: int = 0
    recent: int = 0                  # raw count, last 3 days (display)
    prior: int = 0                   # raw count, the 3 days before that (display)
    recent_share: float = 0.0        # 0-1: the theater's headlines / all headlines in the recent editions
    prior_share: float = 0.0         # same for the prior window; 0 also when that window has no editions
    trend: Literal["heating", "steady", "cooling", "new"] = "steady"
    first_seen: str = ""
    heat: float = 0.0                # share of coverage (per 100 headlines), weighted up when heating or new
    by_class: dict[str, ClassShare] = Field(default_factory=dict)   # per source class (shares are the mean of these)
    novelty: dict[str, Any] = Field(default_factory=dict)           # see ``novelty.measure``; {} on old boards
    state: str = ""                  # new | active | quiet (see ``focus``); "" on old boards
    last_novel: str = ""             # newest date anything new was seen for this theater


COVERAGE_LABELS = {"heating": "rising coverage", "steady": "steady coverage", "cooling": "falling coverage",
                   "new": "newly reported"}


def coverage_label(trend: str) -> str:
    """The reader-facing name of a stored ``trend``.

    Three different things are easy to confuse, so the data keeps them apart: ``trend`` (and ``heat``) is
    COVERAGE momentum, the theater's share of headlines against the window before; it says nothing about
    how bad things are. ``escalation`` is the situation itself, judged from the evidence. Pulse ``band`` is
    severity. Stored names stay as they are (back-compat); ``coverage`` is the label to show."""
    return COVERAGE_LABELS.get(trend, "steady coverage" if trend else "")


# ── the brief ─────────────────────────────────────────────────────────────────────────────────
class TimelineItem(BaseModel):
    date: str                        # YYYY-MM-DD
    what: str
    actors: list[str] = Field(default_factory=list)
    verification: Verification = "reported"
    source: str = ""                 # URL


class Relation(BaseModel):
    """Who is doing what to whom — one edge of the actor map."""

    source: str
    target: str
    kind: Literal["strikes", "sabotage", "coerces", "sanctions", "supports", "negotiates", "deters", "other"]
    note: str = ""
    date: str = ""


class Escalation(BaseModel):
    direction: Literal["rising", "steady", "easing", "unclear"] = "unclear"
    pace: Literal["fast", "gradual", "flat"] = "gradual"
    assessment: str = ""             # an ASSESSMENT, in estimative language, with its basis


class Effect(BaseModel):
    effect: str
    likelihood: Literal["almost certain", "likely", "roughly even", "unlikely", "remote"] = "roughly even"
    watch_for: str = ""


class Indicator(BaseModel):
    signal: str
    status: Literal["not seen", "emerging", "observed"] = "not seen"
    meaning: str = ""                # what it would mean if it shows
    previous_status: str = ""        # its status in our last brief ("" when the signal is new)


class Change(BaseModel):
    """One thing that moved since our last brief — continuity is the first job of a repeat brief."""

    what: str
    kind: Literal["escalated", "eased", "new", "resolved", "unchanged"]
    basis: str = ""                  # the evidence that moved it


class Judgment(BaseModel):
    """A key judgment as a scored forecast: falsifiable, dated, and checkable by a stranger later."""

    statement: str                   # a claim about the future that events can prove wrong
    probability: int                 # percent, 1–99
    horizon: str                     # YYYY-MM-DD, when it should be decidable
    basis: str = ""
    resolves_yes_if: str = ""        # what public reporting would have to show for YES
    resolves_no_if: str = ""         # ...and for NO

    @field_validator("probability", mode="before")
    @classmethod
    def _clamp(cls, v: Any) -> int:
        return max(1, min(99, int(v)))


class Hypothesis(BaseModel):
    """One competing explanation of the theater's core question (analysis of competing hypotheses)."""

    hypothesis: str
    consistent_with: str = ""        # evidence that fits it
    inconsistent_with: str = ""      # evidence that cuts against it
    plausibility: Literal["leading", "plausible", "unlikely"] = "plausible"


class Brief(BaseModel):
    title: str
    bottom_line: str                 # 2–3 sentences: what matters, how sure we are
    situation: str = ""              # where things stand, factually
    escalation: Escalation = Field(default_factory=Escalation)
    timeline: list[TimelineItem] = Field(default_factory=list)
    relations: list[Relation] = Field(default_factory=list)
    second_order: list[Effect] = Field(default_factory=list)
    peripheral: list[Effect] = Field(default_factory=list)   # things outside the core worth watching
    indicators: list[Indicator] = Field(default_factory=list)
    unknowns: list[str] = Field(default_factory=list)
    pulses: list[str] = Field(default_factory=list)          # exact Pulse NAMES this theater bears on
    changes: list[Change] = Field(default_factory=list)      # since our last brief, most important first
    judgments: list[Judgment] = Field(default_factory=list)  # 2–4 scored forecasts
    alternatives: list[Hypothesis] = Field(default_factory=list)   # the red team: competing explanations
    would_change_our_mind: list[str] = Field(default_factory=list)


# ── the daily report ──────────────────────────────────────────────────────────────────────────
# Curation, not analysis: what significantly happened per live theater, who said what, with dates
# and sources, plus the older items the reader needs for context. The deep brief stays the
# occasional dive; the daily links to it. Public shape: see ``publishing/intel_page.py``.
class Statement(BaseModel):
    who: str
    role: str = ""
    said: str                        # a paraphrase, or an exact quote of at most 25 words when quote=True
    quote: bool = False
    when: str = ""
    source: str = ""                 # URL


class Place(BaseModel):
    """Where a development happened, as the writer's best coordinates for a named city or site. The desk
    validates it against the basemap and drops it when it does not hold; country "sea" marks a sea lane."""

    name: str
    country: str = ""
    lat: float
    lon: float


class KeyFigure(BaseModel):
    """A number the researched evidence states, nothing computed. ``baseline`` only when the source gives one."""

    label: str
    value: float
    unit: str = ""
    baseline: float | None = None
    baseline_label: str = ""
    as_of: str = ""                  # YYYY-MM-DD the source gives the number for
    source: str = ""                 # URL, must be one the research cited


class Development(BaseModel):
    headline: str
    detail: str = ""
    when: str = ""                   # YYYY-MM-DD (or a range) when known
    where: str = ""
    actors: list[str] = Field(default_factory=list)
    statements: list[Statement] = Field(default_factory=list, description=(
        "The statements this development rests on: who said it, their role, the date and the transcript "
        "URL from STATEMENTS ON RECORD as `source`. Empty only when the development rests on no statement."))
    significance: str = ""           # why it matters, in a line
    verification: Verification = "reported"
    sources: list[str] = Field(default_factory=list)
    place: Place | None = None       # best coordinates for where it happened; validated, else dropped


class ContextItem(BaseModel):
    """An OLDER event the reader needs in order to understand today."""

    what: str
    when: str = ""
    why_relevant: str = ""
    source: str = ""
    verification: Verification = "reported"   # researched only with a cited source our research holds


class DailyChange(BaseModel):
    what: str
    kind: Literal["escalated", "eased", "new", "resolved", "unchanged"]


class DailyEscalation(BaseModel):
    direction: Literal["rising", "steady", "easing", "unclear"] = "unclear"
    pace: Literal["fast", "gradual", "flat"] = "gradual"


class PulseProposal(BaseModel):
    """A dimension the theater bears on that no listed Pulse measures (calm at the low end, extreme at the high)."""

    name: str
    question: str
    low_end: str
    high_end: str
    why: str = ""


class SectionDraft(BaseModel):
    """What the section writer returns; the engine adds temperature, Pulse numbers and the brief link."""

    bottom_line: str
    escalation: DailyEscalation = Field(default_factory=DailyEscalation)
    since_yesterday: list[DailyChange] = Field(default_factory=list)
    developments: list[Development] = Field(default_factory=list)
    context: list[ContextItem] = Field(default_factory=list)
    outlook: str = ""
    watch_next: list[str] = Field(default_factory=list)
    key_figures: list[KeyFigure] = Field(default_factory=list)   # 0-4, only numbers the research states
    pulses: list[str] = Field(default_factory=list)          # exact Pulse NAMES this theater bears on
    pulse_proposals: list[PulseProposal] = Field(default_factory=list)
    key_statements: list[str] = Field(default_factory=list,  # [S#] tags from STATEMENTS ON RECORD, most consequential first
                                      description="Up to five [S#] tags of the statements on record that matter most, "
                                                  "most consequential first.")


class CrossTheater(BaseModel):
    theaters: list[str] = Field(default_factory=list)       # theater names
    link: str = ""


class DaySummary(BaseModel):
    headline: str
    the_day: list[str] = Field(default_factory=list)        # 3-6 one-sentence bullets, most important first
    cross_theater: list[CrossTheater] = Field(default_factory=list)
