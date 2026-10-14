"""
Extraction: one structured model call reads a ``Material`` and lists the ENUMERATED, entity-level events in it
(a strike on a named power plant, the seizure of a named vessel, the designation of a named company) as candidates.

The model reads and judges; the harness checks mechanically afterwards, so a candidate survives only if
it cites items of the material, its name appears in them, its sources are THEIR urls (never the model's), its date
is plausible, its claimant is traceable to the text (or the outlet that carried it), and any coordinates agree with
the country it names. Nothing here touches the ledger: ``ingest`` resolves candidates to assets and writes them.

The wire schema is flat (no unions: the house model provider rejects ``oneOf``/``anyOf``).
"""

from __future__ import annotations

from collections.abc import Callable
from datetime import date, timedelta
from typing import Any
from urllib.parse import urlsplit

from pydantic import BaseModel, Field

from .contracts import (NOTE_CHARS, AssetType, Confidence, Status, fold, valid_day)
from .materials import Material

ROLE = """\
You keep a ledger of named things and what has been said about their state: which power plant, substation, refinery,
fuel depot, port, bridge, airbase, base or dam was hit, which vessel was seized, which named entity was designated.
Prose buries these. A paragraph saying "strikes on six power plants" is useful once and forgotten; an entry per named
facility, with who said what about it and when, can be mapped, counted, checked against later reports and told apart
from what was only claimed. That is the whole reason this list exists, so be exact about WHO is saying it.

List an event for every NAMED facility, vessel or entity the text says something dated about. Skip anything not named
(\"energy infrastructure\", \"several depots\"), skip general commentary, and skip a thing the text only mentions
in passing with no event. An empty list is a correct answer.

Claim is not confirmation. The `status` follows the speaker, never the outlet's tone:
- claimed_struck: a PARTY to the fight says it struck or hit the thing; `claimant` is that party. This stays
  claimed_struck however firmly it is worded, until someone else says damage occurred.
- reported_damaged: damage is reported by the owner, authorities, witnesses or media without independent confirmation.
- confirmed_damaged: the owner or operator, a neutral authority or imagery analysis states damage did occur.
- destroyed: described as destroyed or put out of operation entirely, by the claimant you name.
- restored: back in operation or repaired. operational: stated to be running, e.g. when a claim is denied.
- seized / designated: a vessel or asset taken, or a person or company put on a list (the claimant is who acted).
- unknown: only when the text names the event but not its outcome.
Two sources saying different things about one facility are two entries, not one merged one.

Fields. `name_as_written`: the name EXACTLY as the cited item writes it (the harness checks it appears there).
`known_as`: the name by which you know it well (other spelling, English form), or empty. `type` is what it is;
`country` its ISO alpha-2 code, or empty if the text does not make it clear. `place`: the nearest city or district.
Give `lat`/`lon` and set `located` only if you know where this specific facility is; a wrong position is worse than
none, and the harness rejects one that falls outside the country you named. `claimant`: who says it, as precisely as the
text allows ("Russian Ministry of Defence", "Ukrenergo", "Governor of Kharkiv region"); if the text gives no speaker,
the outlet that carried it. `date`: the day the event happened or was claimed (YYYY-MM-DD) when the text gives or implies
it from the item's date, else empty. `confidence`: how sure you are that the TEXT says this (not that the event is true).
`quote`: the shortest passage of the cited item that carries it, copied exactly. `item_ids`: the items that state it.
"""


class CandidateEvent(BaseModel):
    item_ids: list[str] = Field(description="Ids of the items that state this event.")
    name_as_written: str = Field(description="The facility, vessel or entity name exactly as the cited item writes it.")
    known_as: str = Field(default="", description="Another spelling or the English form you know it by, or empty.")
    type: AssetType = "other"
    country: str = Field(default="", description="ISO 3166-1 alpha-2, or empty.")
    place: str = Field(default="", description="Nearest city or district, or empty.")
    located: bool = Field(default=False, description="True only if lat/lon are where this specific facility is.")
    lat: float = 0.0
    lon: float = 0.0
    status: Status
    claimant: str = Field(description="Who says it, as precisely as the text allows.")
    date: str = Field(default="", description="YYYY-MM-DD, or empty.")
    time: str = Field(default="", description="HH:MM if the text gives the hour, else empty.")
    confidence: Confidence = "medium"
    quote: str = Field(default="", description="Exact words from the cited item, as short as will do.")


class CandidatePlan(BaseModel):
    events: list[CandidateEvent] = Field(default_factory=list)


class Candidate(BaseModel):
    """A model proposal that passed the harness checks, with provenance stamped from the material."""

    name: str
    known_as: str = ""
    type: str
    country: str = ""
    place: str = ""
    lat: float | None = None
    lon: float | None = None
    status: str
    claimant: str
    occurred_on: str
    occurred_at: str = ""
    confidence: str = "medium"
    sources: list[str]
    note: str = ""
    item_ids: list[str]


def _task(m: Material) -> str:
    items = "\n".join(f"[{i.id}]{f' ({i.when})' if i.when else ''} {i.text}" for i in m.items)
    return (f"SOURCE: {m.label}\nTODAY (the day relative dates hang from): {m.default_date or 'unknown'}\n\n"
            f"ITEMS (cite by id):\n{items}\n\nTASK: list the named facility, vessel and entity events these items state.")


def _norm(s: str) -> str:
    return " ".join(fold(s).replace("’", "'").split())


def _host(url: str) -> str:
    return urlsplit(url).netloc.removeprefix("www.")


def _claimant(raw: str, cited_text: str, urls: list[str]) -> str:
    """The claimant if the text (or the outlet carrying it) bears it out; else the outlet, never an invented speaker."""
    c = " ".join(raw.split())
    hosts = " ".join(_host(u) for u in urls)
    words = [w[:5] for w in _norm(c).replace("'s", " ").split() if len(w) >= 4]
    haystack = f"{_norm(cited_text)} {_norm(hosts)}"
    if c and (c.casefold().startswith("ohmega") or any(w in haystack for w in words)):
        return c
    return f"reported via {_host(urls[0])}" if urls else ""


def validate(plan: Any, m: Material, *, today: date | None = None, iso_at: Callable[[float, float], str] | None = None,
             valid_country: Callable[[str], bool] | None = None) -> tuple[list[Candidate], list[str]]:
    """The candidates that stand on the material, and a line per candidate dropped or repaired."""
    today = today or date.today()
    floor, ceil = (today - timedelta(days=400)).isoformat(), (today + timedelta(days=1)).isoformat()
    by_id = {i.id: i for i in m.items}
    out: list[Candidate] = []
    notes: list[str] = []
    for ev in getattr(plan, "events", None) or []:
        tag = (ev.name_as_written or "?")[:40]
        cited = [by_id[i] for i in dict.fromkeys(ev.item_ids) if i in by_id]
        text = " ".join(i.text for i in cited)
        urls = list(dict.fromkeys(u for i in cited for u in i.urls))
        if not cited:
            notes.append(f"{tag}: dropped, cites no item of the material")
        elif not ev.name_as_written.strip() or _norm(ev.name_as_written) not in _norm(text):
            notes.append(f"{tag}: dropped, the name is not in the items it cites")
        elif not urls:
            notes.append(f"{tag}: dropped, the items it cites carry no source url")
        elif not (claimant := _claimant(ev.claimant, text, urls)):
            notes.append(f"{tag}: dropped, no claimant")
        else:
            day = ev.date.strip()
            if not (valid_day(day) and floor <= day <= ceil):
                day = next((i.when for i in cited if i.when), "") or m.default_date
            if not (valid_day(day) and floor <= day <= ceil):
                notes.append(f"{tag}: dropped, no usable date")
                continue
            if claimant != " ".join(ev.claimant.split()):
                notes.append(f"{tag}: claimant {ev.claimant!r} is not in the text; recorded as {claimant!r}")
            country = ev.country.strip().upper()
            if country and valid_country is not None and not valid_country(country):
                country = ""
            lat = lon = None
            if ev.located and -90 <= ev.lat <= 90 and -180 <= ev.lon <= 180 and (ev.lat or ev.lon):
                there = iso_at(ev.lat, ev.lon) if iso_at else ""
                if country and there and there != country:
                    notes.append(f"{tag}: position {ev.lat:.2f},{ev.lon:.2f} is in {there}, not {country}; position dropped")
                else:
                    lat, lon = round(ev.lat, 5), round(ev.lon, 5)
                    country = country or there
            quote = " ".join(ev.quote.split())
            note = quote[:NOTE_CHARS] if quote and _norm(quote) in _norm(text) else ""
            out.append(Candidate(name=ev.name_as_written.strip(), known_as=ev.known_as.strip(), type=ev.type, country=country,
                                 place=ev.place.strip(), lat=lat, lon=lon, status=ev.status, claimant=claimant,
                                 occurred_on=day, occurred_at=ev.time.strip() if len(ev.time.strip()) == 5 else "",
                                 confidence=ev.confidence, sources=urls[:6], note=note, item_ids=[i.id for i in cited]))
    return out, notes


def extract(m: Material, ask: Callable[[Any, str, str], Any], **check: Any) -> tuple[list[Candidate], list[str], int]:
    """Candidates from a material: one call per batch of items. Returns (candidates, notes, calls). Raises only if the
    model call itself does (the caller decides whether that is fatal; ``ingest`` never lets it be)."""
    cands: list[Candidate] = []
    notes: list[str] = []
    calls = 0
    for batch in m.batches():
        plan = ask(CandidatePlan, ROLE, _task(batch))
        calls += 1
        c, n = validate(plan, batch, **check)
        cands.extend(c)
        notes.extend(n)
    return cands, notes, calls
