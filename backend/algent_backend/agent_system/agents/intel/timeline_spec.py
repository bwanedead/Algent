"""
The timeline contract: a dated sequence the reader scans top to bottom (daily visual kind ``timeline``, native).

Data, never code: ``components/NativeTimeline.tsx`` draws it. Grounding is part of the contract (``ground``): every
event cites facts of the day, its date must be stated by one of them, and no number in its words may be one the
cited facts lack. An event that fails is dropped (named in the report), not patched; fewer than ``MIN_EVENTS`` left
refuses the timeline. Sources are resolved from the cited facts by the producer, never written by the model.
"""

from __future__ import annotations

import re
from datetime import date
from typing import Annotated, Literal

from pydantic import BaseModel, Field

from .visuals_grounding import mentions_date, mentions_place, ungrounded, word_count

Kind = Literal["strike", "statement", "meeting", "decision", "movement", "deadline", "other"]
MIN_EVENTS, MAX_EVENTS = 3, 24
TITLE_WORDS, DETAIL_WORDS = 10, 30
_ISO = re.compile(r"\d{4}-\d{2}-\d{2}")


class Place(BaseModel):
    name: str
    lat: float | None = Field(None, ge=-90, le=90)
    lon: float | None = Field(None, ge=-180, le=180)


class Lane(BaseModel):
    id: str
    label: str                      # an actor or a thread: "Russia", "Diplomacy"


class Source(BaseModel):
    label: str
    url: str = ""


class Event(BaseModel):
    id: str
    date: str                       # YYYY-MM-DD
    time: str = ""                  # HH:MM when the facts give the hour
    title: str                      # at most TITLE_WORDS words
    detail: str = ""                # at most DETAIL_WORDS words
    actors: Annotated[list[str], Field(max_length=4)] = Field(default_factory=list)    # ISO alpha-2 codes
    lane: str = ""                  # a ``Lane.id`` when lanes are used
    kind: Kind = "other"
    place: Place | None = None
    fact_ids: Annotated[list[str], Field(max_length=6)] = Field(default_factory=list)
    sources: list[Source] = Field(default_factory=list)      # filled from the cited facts by the producer


class Timeline(BaseModel):
    title: str
    caption: str
    lanes: Annotated[list[Lane], Field(max_length=4)] = Field(default_factory=list)
    events: Annotated[list[Event], Field(max_length=MAX_EVENTS + 8)]
    now: str = ""                   # the "as of" date, set by the producer
    alt: str = ""


def valid_date(s: str) -> bool:
    try:
        date.fromisoformat(s)
    except ValueError:
        return False
    return bool(_ISO.fullmatch(s))


def ground(tl: Timeline, facts: dict[str, str]) -> list[str]:
    """Drop every event the cited facts do not carry (in place) and return a line per drop or fix; then the
    spec-level problems, each prefixed ``REFUSED``. ``facts`` maps fact id to text (the visual's cited facts)."""
    notes: list[str] = []
    kept: list[Event] = []
    lanes = {ln.id for ln in tl.lanes}
    seen: set[str] = set()
    for e in tl.events:
        cited = " ".join(facts[i] for i in dict.fromkeys(e.fact_ids) if i in facts)
        why = ""
        if e.id in seen:
            why = "duplicate id"
        elif not (cited and all(i in facts for i in e.fact_ids)):
            why = "cites no fact of the visual (or one that is not)"
        elif not valid_date(e.date):
            why = f"date {e.date!r} is not YYYY-MM-DD"
        elif not mentions_date(cited, e.date):
            why = f"no cited fact states {e.date}"
        elif not e.title.strip() or word_count(e.title) > TITLE_WORDS or word_count(e.detail) > DETAIL_WORDS:
            why = f"title over {TITLE_WORDS} or detail over {DETAIL_WORDS} words, or no title"
        elif bad := ungrounded(f"{e.title} {e.detail}", cited):
            why = f"numbers not in its facts ({', '.join(bad[:3])})"
        if why:
            notes.append(f"event {e.id or e.title[:24]!r} dropped: {why}")
            continue
        seen.add(e.id)
        e.actors = [a.upper() for a in e.actors if re.fullmatch(r"[A-Za-z]{2}", a)]
        if e.lane and e.lane not in lanes:
            e.lane = ""
        if e.place and (e.place.lat is None) != (e.place.lon is None):
            e.place.lat = e.place.lon = None
        if e.place and e.place.lat is not None and not mentions_place(cited, e.place.name):
            notes.append(f"event {e.id!r}: place {e.place.name!r} is not in its facts; place removed")
            e.place = None
        kept.append(e)
    tl.events = sorted(kept, key=lambda x: (x.date, x.time))
    if not MIN_EVENTS <= len(tl.events) <= MAX_EVENTS:
        notes.append(f"REFUSED: {len(tl.events)} grounded events, need {MIN_EVENTS} to {MAX_EVENTS}")
    if bad := ungrounded(f"{tl.title} {tl.caption}", " ".join(facts.values())):
        notes.append(f"REFUSED: title or caption carries numbers not in the facts ({', '.join(bad[:3])})")
    used = {e.lane for e in tl.events if e.lane}
    tl.lanes = [ln for ln in tl.lanes if ln.id in used] if len(used) >= 2 else []
    if len(used) < 2:
        for e in tl.events:
            e.lane = ""
    return notes


def refused(notes: list[str]) -> list[str]:
    return [n for n in notes if n.startswith("REFUSED")]


def alt_text(tl: Timeline) -> str:
    """The event list as plain text: the text alternative, and what a reader without script sees."""
    lines = [f"{e.date}{' ' + e.time if e.time else ''}: {e.title}." + (f" {e.detail}" if e.detail else "") for e in tl.events]
    return f"{tl.title}. {tl.caption} " + " ".join(lines)
