"""
The flow contract: goods, energy, money, weapons or people moving between places, and what happens when a route
breaks (daily visual kind ``flow``, native).

Data, never code: ``components/NativeFlow.tsx`` draws it over the site's map (``LiveMap``): curved arcs with
particles moving along them, width in proportion to the amount where the facts state one. A ``disruption`` breaks
named flows or places on a date; the flows it lists in ``reroutes`` are the alternatives that carry the traffic and are
drawn only while the disruption is on. A route through a chokepoint lists that place in ``via``.

The model fills this schema directly (no unions, so it is also the wire schema: ``from_wire`` is the identity and
``ground`` enforces every limit, trimming rather than failing).

Grounding (``ground``): a flow cites facts of the day and both ends (and any ``via``) must be named in them; an amount
is a figure a cited fact holds, otherwise it is cleared and the flow is drawn without a width (never an invented one);
a place's coordinates cannot be checked against prose, the name given to them can; a disruption's date must be stated
by a cited fact that also names what it breaks; words carry no number the facts lack. What fails is dropped and named
in the report; too few flows refuses the visual.
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field

from .timeline_spec import Source, valid_date
from .visuals_grounding import mentions_date, mentions_entity, ungrounded, word_count

Role = Literal["source", "sink", "hub", "chokepoint"]
MIN_FLOWS, MAX_FLOWS, MAX_PLACES, MAX_DISRUPTIONS = 2, 24, 14, 3
LABEL_WORDS, DETAIL_WORDS, EFFECT_WORDS = 4, 20, 30


class Place(BaseModel):
    id: str
    name: str                       # at most LABEL_WORDS words; a cited fact speaks of it
    role: Role = "hub"
    lat: float
    lon: float


class Flow(BaseModel):
    id: str
    source: str                     # a ``Place.id``
    target: str
    commodity: str                  # "crude oil", "wheat", "arms", "remittances": at most LABEL_WORDS words
    amount: float = 0.0             # 0 = no figure; else a figure a cited fact holds, in ``unit``
    unit: str = ""                  # "million barrels a day"
    period: str = ""                # "per day", "in 2025"
    via: list[str] = Field(default_factory=list)     # ``Place.id`` waypoints in travel order (a chokepoint)
    detail: str = ""                # at most DETAIL_WORDS words, only from the cited facts
    fact_ids: list[str] = Field(default_factory=list)
    sources: list[Source] = Field(default_factory=list)      # filled from the cited facts by the producer


class Disruption(BaseModel):
    id: str
    date: str                       # YYYY-MM-DD
    breaks: list[str] = Field(default_factory=list)          # ids of flows or places that stop
    reroutes: list[str] = Field(default_factory=list)        # ids of flows that carry the traffic instead (drawn only now)
    effect: str = ""                # at most EFFECT_WORDS words: what happens, only from the cited facts
    fact_ids: list[str] = Field(default_factory=list)
    sources: list[Source] = Field(default_factory=list)


class FlowMap(BaseModel):
    title: str
    caption: str
    places: list[Place]
    flows: list[Flow]
    disruptions: list[Disruption] = Field(default_factory=list)
    bounds: list[float] = Field(default_factory=list)        # [west, south, east, north], set by ``frame``
    alt: str = ""


FlowWire = FlowMap                  # no unions in this schema: the strict spec is what the model fills


def from_wire(wire: FlowMap) -> tuple[FlowMap, list[str]]:
    return wire, []


def frame(spec: FlowMap, pad: float = 0.15) -> list[float]:
    """[west, south, east, north] around every place, padded, never degenerate."""
    if not spec.places:
        return []
    w, e = min(p.lon for p in spec.places), max(p.lon for p in spec.places)
    s, n = min(p.lat for p in spec.places), max(p.lat for p in spec.places)
    dx, dy = max(e - w, 2.0), max(n - s, 2.0)
    return [round(max(-180, w - dx * pad), 3), round(max(-85, s - dy * pad), 3),
            round(min(180, e + dx * pad), 3), round(min(85, n + dy * pad), 3)]


def _text(facts: dict[str, str], ids: list[str]) -> str:
    return " ".join(facts[x] for x in dict.fromkeys(ids) if x in facts)


def _flow_problem(f: Flow, names: dict[str, str], facts: dict[str, str], notes: list[str]) -> str:
    f.fact_ids = f.fact_ids[:6]
    cited = _text(facts, f.fact_ids)
    if not f.id.strip() or not cited or not all(x in facts for x in f.fact_ids):
        return "no id, or cites no fact of the visual (or one that is not)"
    ends = [f.source, f.target, *f.via[:3]]
    if f.source == f.target or any(i not in names for i in ends):
        return "its ends or waypoints are not places of the map"
    for i in ends:
        if not mentions_entity(cited, names[i]):
            return f"{names[i]!r} is not named by its facts"
    if not f.commodity.strip() or word_count(f.commodity) > LABEL_WORDS:
        return f"commodity empty or over {LABEL_WORDS} words"
    if word_count(f.detail) > DETAIL_WORDS or ungrounded(f.detail, cited):
        return f"detail over {DETAIL_WORDS} words or carries numbers not in its facts"
    if f.amount and (f.amount < 0 or not f.unit.strip() or ungrounded(f"{f.amount:g}", cited)):
        notes.append(f"flow {f.id!r}: amount cleared: not a figure its facts hold (drawn without a width)")
        f.amount, f.unit, f.period = 0.0, "", ""
    if not f.amount:
        f.unit = f.period = ""
    f.via = f.via[:3]
    return ""


def _disruption_problem(d: Disruption, flows: dict[str, Flow], names: dict[str, str], facts: dict[str, str]) -> str:
    d.fact_ids = d.fact_ids[:6]
    cited = _text(facts, d.fact_ids)
    if not d.id.strip() or not cited or not all(x in facts for x in d.fact_ids):
        return "no id, or cites no fact of the visual (or one that is not)"
    if not valid_date(d.date) or not mentions_date(cited, d.date):
        return f"no cited fact states {d.date!r}"
    d.breaks = [b for b in dict.fromkeys(d.breaks) if b in flows or b in names]
    d.reroutes = [r for r in dict.fromkeys(d.reroutes) if r in flows and r not in d.breaks]
    if not d.breaks:
        return "breaks nothing on the map"
    for b in d.breaks:     # the facts it cites must name what breaks (a flow: either end or a waypoint)
        named = [names[b]] if b in names else [names[i] for i in (flows[b].source, flows[b].target, *flows[b].via)]
        if not any(mentions_entity(cited, n) for n in named):
            return f"its facts do not name what breaks ({b})"
    if not d.effect.strip() or word_count(d.effect) > EFFECT_WORDS:
        return f"effect empty or over {EFFECT_WORDS} words"
    if bad := ungrounded(d.effect, cited):
        return f"effect carries numbers not in its facts ({', '.join(bad[:2])})"
    return ""


def ground(spec: FlowMap, facts: dict[str, str]) -> list[str]:
    """Drop flows and disruptions the cited facts do not carry (in place); return a line per drop or fix, then any
    spec-level problem prefixed ``REFUSED``. ``facts`` maps fact id to text (the visual's cited facts)."""
    notes: list[str] = []
    places: dict[str, Place] = {}
    for p in spec.places:
        if (p.id.strip() and p.id not in places and p.name.strip() and word_count(p.name) <= LABEL_WORDS
                and -90 <= p.lat <= 90 and -180 <= p.lon <= 180):
            places[p.id] = p
        else:
            notes.append(f"place {p.id or p.name[:20]!r} dropped: no id, duplicate, name empty or over {LABEL_WORDS} words, or off the globe")
    names = {i: p.name for i, p in places.items()}
    flows: dict[str, Flow] = {}
    for f in spec.flows:
        if f.id in flows:
            notes.append(f"flow {f.id!r} dropped: duplicate id")
        elif why := _flow_problem(f, names, facts, notes):
            notes.append(f"flow {f.id!r} dropped: {why}")
        else:
            flows[f.id] = f
    spec.flows = list(flows.values())[:MAX_FLOWS]
    flows = {f.id: f for f in spec.flows}
    used = {i for f in spec.flows for i in (f.source, f.target, *f.via)}
    spec.places = [p for i, p in places.items() if i in used][:MAX_PLACES]
    names = {p.id: p.name for p in spec.places}
    kept: list[Disruption] = []
    for d in spec.disruptions:
        if why := _disruption_problem(d, flows, names, facts):
            notes.append(f"disruption {d.id!r} dropped: {why}")
        elif d.id not in {k.id for k in kept}:
            kept.append(d)
    spec.disruptions = sorted(kept, key=lambda d: d.date)[:MAX_DISRUPTIONS]
    broken = {r for d in spec.disruptions for r in d.reroutes}
    if len(spec.flows) - len(broken) < 1:
        notes.append("REFUSED: every flow is a reroute; nothing flows normally")
    if len(spec.flows) < MIN_FLOWS:
        notes.append(f"REFUSED: {len(spec.flows)} grounded flows, need {MIN_FLOWS} to {MAX_FLOWS}")
    if bad := ungrounded(f"{spec.title} {spec.caption}", " ".join(facts.values())):
        notes.append(f"REFUSED: title or caption carries numbers not in the facts ({', '.join(bad[:3])})")
    spec.bounds = frame(spec)
    return notes


def alt_text(spec: FlowMap) -> str:
    """The flows and disruptions as plain text: the alternative to the animated map."""
    by = {p.id: p.name for p in spec.places}
    lines = []
    for f in spec.flows:
        amount = f" ({f.amount:g} {f.unit}{' ' + f.period if f.period else ''})" if f.amount else ""
        lines.append(f"{f.commodity.capitalize()} flows from {by.get(f.source, f.source)} to {by.get(f.target, f.target)}{amount}." +
                     (f" {f.detail}" if f.detail else ""))
    lines += [f"{d.date}: {d.effect}" for d in spec.disruptions]
    return f"{spec.title}. {spec.caption} " + " ".join(lines)
