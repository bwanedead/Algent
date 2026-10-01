"""
A Pulse's current state, computed from its influence log — never stored as a mutable number.

Replaying the log is what makes the ledger auditable: "what did Ohmega believe on Aug 14?" is the
same function with a cutoff, and changing how bands or velocity are computed recomputes history
instead of migrating it.

Position rule: the position is the proposed position of the latest APPLIED influence. Blind
reassessments never set it — they are the anchoring check, recorded as a gap against the position
held at that moment. A gap wider than one band of the ruler flags the Pulse for reconciliation;
the two are never silently averaged.

Absolute votes: every reader also records where it thinks reality sits ignoring the history. No
reader sees the whole picture — the Pulse IS the net of many partial ones — so no single absolute
read moves it. Instead the recent votes, one per independent source, are summarised here and shown
to every later reader; a history that readers across different research keep disagreeing with is
pulled back toward reality by them, one argued reading at a time. There is no arbiter above the
collective (operator, 09-30): the view is the voters' own, with newer votes counting for more.
"""

from __future__ import annotations

from datetime import datetime, timedelta

from pydantic import BaseModel, Field

from .contracts import BANDS, Influence, band_of

#: A blind read that disagrees with the held position by more than one band means the two cannot
#: both be right about which category the world is in. One band width is taken from the ruler
#: itself, not chosen: the bands ARE the resolution we claim.
RECONCILE_GAP = BANDS[1][0] - BANDS[0][0]


#: How many recent independent votes make up the collective absolute view — the same depth of
#: memory a reader is shown as past readings (framing.py), so votes and history cover one span.
VOTES = 8


def _voter(inf: Influence) -> str:
    """One research effort is one voter, however many readings it produced."""
    s = inf.source
    return s.profile_id or s.run_id or inf.key


def absolute_votes(log: list[Influence]) -> list[Influence]:
    """The latest absolute read of each of the most recent independent sources, oldest first."""
    seen, out = set(), []
    for inf in sorted(log, key=lambda i: i.at, reverse=True):
        if inf.mode == "blind" or inf.absolute_position is None or _voter(inf) in seen:
            continue
        seen.add(_voter(inf))
        out.append(inf)
        if len(out) == VOTES:
            break
    return out[::-1]


def collective_view(votes: list[Influence]) -> float:
    """The weighted median of the votes (oldest first), each weighted by its recency rank.

    Newer readers saw newer evidence, so they count for more, but no single vote decides: the
    median moves only when enough of the weight sits on one side. Rank, not age in days, sets the
    weight, so a quiet Pulse's few votes are not discounted just for being old.
    """
    ranked = sorted(((v.absolute_position, rank) for rank, v in enumerate(votes, start=1)),
                    key=lambda pair: pair[0])
    half, seen = sum(rank for _, rank in ranked) / 2, 0
    for value, rank in ranked:
        seen += rank
        if seen >= half:
            return float(value)
    return float(ranked[-1][0])


class Point(BaseModel):
    at: str
    position: float
    band: str


class PulseState(BaseModel):
    pulse_id: str
    position: float | None = None        # None until seeded
    band: str = ""
    velocity_7d: float | None = None     # position change over the window (None: no history)
    velocity_30d: float | None = None
    confidence: str = ""                 # high / medium / low (from the latest applied influence)
    last_assessed: str = ""              # any influence at all
    last_value_change: str = ""
    last_band_change: str = ""
    evidence_through: str = ""
    anchoring_gap: float | None = None   # |latest blind − position held then|
    absolute_view: float | None = None   # recency-weighted median of the recent independent votes
    absolute_voters: int = 0
    needs_reconciliation: bool = False
    influences: int = 0
    history: list[Point] = Field(default_factory=list)       # every value move
    band_changes: list[Point] = Field(default_factory=list)  # the publishable subset


def _ts(value: str) -> datetime:
    return datetime.fromisoformat(value.replace("Z", "+00:00"))


def project(pulse_id: str, log: list[Influence], *, as_of: str | None = None) -> PulseState:
    """Replay a Pulse's log (optionally only up to ``as_of``) into its state."""
    cutoff = _ts(as_of) if as_of else None
    entries = sorted((i for i in log if cutoff is None or _ts(i.at) <= cutoff), key=lambda i: i.at)
    state = PulseState(pulse_id=pulse_id, influences=len(entries))
    for inf in entries:
        state.last_assessed = inf.at
        if inf.evidence_through and inf.evidence_through > state.evidence_through:
            state.evidence_through = inf.evidence_through
        if inf.mode == "blind":
            if inf.proposed_position is not None and state.position is not None:
                state.anchoring_gap = round(abs(inf.proposed_position - state.position), 1)
                state.needs_reconciliation = state.anchoring_gap > RECONCILE_GAP
            continue
        if inf.decision == "reconcile":
            state.needs_reconciliation = True
            continue
        if inf.mode == "reassess" and inf.decision in ("applied", "no_change"):
            state.needs_reconciliation = False   # a full reassessment IS the reconciliation
        if inf.decision != "applied" or inf.proposed_position is None:
            continue
        new = float(inf.proposed_position)
        state.confidence = inf.confidence.overall()
        if state.position is None or new != state.position:
            point = Point(at=inf.at, position=new, band=band_of(new))
            if state.position is None or band_of(new) != band_of(state.position):
                state.band_changes.append(point)
                state.last_band_change = inf.at
            state.history.append(point)
            state.last_value_change = inf.at
            state.position = new
    votes = absolute_votes(entries)
    if votes:
        state.absolute_view = round(collective_view(votes), 1)
        state.absolute_voters = len(votes)
    if state.position is not None:
        state.band = band_of(state.position)
        now = cutoff or (_ts(state.last_assessed) if state.last_assessed else None)
        if now is not None:
            state.velocity_7d = _velocity(state.history, now, days=7)
            state.velocity_30d = _velocity(state.history, now, days=30)
    return state


def _velocity(history: list[Point], now: datetime, *, days: int) -> float | None:
    """Position now minus the position held ``days`` ago (None when there was none yet)."""
    if not history:
        return None
    start = now - timedelta(days=days)
    before = [p for p in history if _ts(p.at) <= start]
    if not before:
        return None
    return round(history[-1].position - before[-1].position, 1)
