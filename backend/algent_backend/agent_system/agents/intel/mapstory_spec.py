"""
The map story contract: what moved where and when, as steps over the site's map (daily visual kind ``mapstory``).

Data, never code: ``components/MapStory.tsx`` plays it over MapLibre. A step is a date, a caption and the features
that CHANGE at that step: ``show`` introduces a feature or, with an id already on the map, moves/replaces it
(points glide, routes draw themselves, areas and range rings fade in); ``hide`` removes ids. State carries forward,
so a step lists only what is new.

Grounding (``ground``): a step cites facts of the day and its date must be stated by one of them; every feature must
name the place it is at, and that place must be one a cited fact speaks of (coordinates cannot be checked against
prose, the name given to them can); a range ring's radius must be a figure the cited facts hold; words carry no
number the facts lack. What fails is dropped and named in the report; fewer than ``MIN_STEPS`` left refuses it.
"""

from __future__ import annotations

import math
from typing import Annotated, Literal, Union

from pydantic import BaseModel, Field

from .timeline_spec import Source, valid_date
from .visuals_grounding import mentions_date, mentions_place, ungrounded, word_count

Tone = Literal["ink", "accent", "warn", "cool", "hot", "good"]
MIN_STEPS, MAX_STEPS, MAX_FEATURES = 2, 12, 40
LABEL_WORDS, CAPTION_WORDS = 6, 35


class Pt(BaseModel):
    lat: float = Field(ge=-90, le=90)
    lon: float = Field(ge=-180, le=180)


class _F(BaseModel):
    id: str
    label: str = ""                 # on the map, at most LABEL_WORDS words
    tone: Tone = "accent"
    place: str = ""                 # the named place it is at (a route: ``places``)


class Point(_F):
    type: Literal["point"] = "point"
    at: Pt


class Route(_F):
    type: Literal["route"] = "route"
    path: Annotated[list[Pt], Field(min_length=2, max_length=24)]
    places: Annotated[list[str], Field(min_length=2, max_length=6)] = Field(default_factory=list)   # named stops
    arrow: bool = True              # direction of travel: path order


class Area(_F):
    type: Literal["area"] = "area"
    ring: Annotated[list[Pt], Field(min_length=3, max_length=40)]


class Range(_F):
    type: Literal["range"] = "range"    # a range ring on the ground about ``at``
    at: Pt
    radius_km: float = Field(gt=0, le=20000)


Feature = Annotated[Union[Point, Route, Area, Range], Field(discriminator="type")]


class Step(BaseModel):
    date: str                       # YYYY-MM-DD
    caption: str                    # at most CAPTION_WORDS words, what changed
    fact_ids: Annotated[list[str], Field(max_length=6)] = Field(default_factory=list)
    show: Annotated[list[Feature], Field(max_length=16)] = Field(default_factory=list)
    hide: list[str] = Field(default_factory=list)
    sources: list[Source] = Field(default_factory=list)      # filled from the cited facts by the producer


class MapStory(BaseModel):
    title: str
    caption: str
    steps: Annotated[list[Step], Field(max_length=MAX_STEPS + 4)]
    bounds: list[float] = Field(default_factory=list)        # [west, south, east, north], set by ``frame``
    alt: str = ""


def _ring_km(p: Pt, km: float) -> list[Pt]:
    k = 111.32
    return [Pt(lat=max(-90, min(90, p.lat + km / k * math.sin(a))), lon=max(-180, min(180, p.lon + km / (k * max(math.cos(math.radians(p.lat)), 0.05)) * math.cos(a))))
            for a in (i * math.pi / 8 for i in range(16))]


def points_of(f: Feature) -> list[Pt]:
    """Every coordinate a feature occupies (a range ring: its circle)."""
    if isinstance(f, Point):
        return [f.at]
    if isinstance(f, Route):
        return f.path
    if isinstance(f, Area):
        return f.ring
    return _ring_km(f.at, f.radius_km)


def frame(story: MapStory, pad: float = 0.12) -> list[float]:
    """[west, south, east, north] around every feature, padded, never degenerate."""
    pts = [p for s in story.steps for f in s.show for p in points_of(f)]
    if not pts:
        return []
    w, e = min(p.lon for p in pts), max(p.lon for p in pts)
    s, n = min(p.lat for p in pts), max(p.lat for p in pts)
    dx, dy = max(e - w, 1.0), max(n - s, 1.0)
    return [round(max(-180, w - dx * pad), 3), round(max(-85, s - dy * pad), 3),
            round(min(180, e + dx * pad), 3), round(min(85, n + dy * pad), 3)]


def _feature_problem(f: Feature, cited: str) -> str:
    if not f.id.strip() or word_count(f.label) > LABEL_WORDS:
        return f"no id, or label over {LABEL_WORDS} words"
    names = f.places if isinstance(f, Route) else [f.place]
    if not names or not all(n.strip() and mentions_place(cited, n) for n in names):
        return f"place {names} is not one its facts speak of"
    if isinstance(f, Range) and ungrounded(f"{f.radius_km:g}", cited):
        return f"radius {f.radius_km:g} km is not a figure its facts hold"
    if bad := ungrounded(f.label, cited):
        return f"label carries numbers not in its facts ({', '.join(bad[:2])})"
    return ""


def ground(story: MapStory, facts: dict[str, str]) -> list[str]:
    """Drop steps and features the cited facts do not carry (in place); return a line per drop, then any
    spec-level problem prefixed ``REFUSED``. ``facts`` maps fact id to text (the visual's cited facts)."""
    notes: list[str] = []
    steps: list[Step] = []
    for i, s in enumerate(story.steps):
        cited = " ".join(facts[x] for x in dict.fromkeys(s.fact_ids) if x in facts)
        why = ""
        if not cited or not all(x in facts for x in s.fact_ids):
            why = "cites no fact of the visual (or one that is not)"
        elif not valid_date(s.date) or not mentions_date(cited, s.date):
            why = f"no cited fact states {s.date!r}"
        elif not s.caption.strip() or word_count(s.caption) > CAPTION_WORDS:
            why = f"caption empty or over {CAPTION_WORDS} words"
        elif bad := ungrounded(s.caption, cited):
            why = f"caption carries numbers not in its facts ({', '.join(bad[:3])})"
        if why:
            notes.append(f"step {i + 1} ({s.date}) dropped: {why}")
            continue
        keep: list[Feature] = []
        for f in s.show:
            if p := _feature_problem(f, cited):
                notes.append(f"step {i + 1}: {f.type} {f.id!r} dropped: {p}")
            elif f.id not in {k.id for k in keep}:
                keep.append(f)
        s.show = keep
        shown = {f.id for f in keep}
        s.hide = [h for h in dict.fromkeys(s.hide) if h not in shown]
        steps.append(s)
    story.steps = sorted(steps, key=lambda s: s.date)
    if not MIN_STEPS <= len(story.steps) <= MAX_STEPS:
        notes.append(f"REFUSED: {len(story.steps)} grounded steps, need {MIN_STEPS} to {MAX_STEPS}")
    total = sum(len(s.show) for s in story.steps)
    if not 1 <= total <= MAX_FEATURES:
        notes.append(f"REFUSED: {total} features on the map, need 1 to {MAX_FEATURES}")
    if bad := ungrounded(f"{story.title} {story.caption}", " ".join(facts.values())):
        notes.append(f"REFUSED: title or caption carries numbers not in the facts ({', '.join(bad[:3])})")
    known: set[str] = set()
    for s in story.steps:      # a hide of something never shown is noise
        s.hide = [h for h in s.hide if h in known]
        known |= {f.id for f in s.show}
    story.bounds = frame(story)
    return notes


def alt_text(story: MapStory) -> str:
    """The steps as plain text: the alternative to the animated map."""
    return f"{story.title}. {story.caption} " + " ".join(f"{s.date}: {s.caption}." for s in story.steps)
