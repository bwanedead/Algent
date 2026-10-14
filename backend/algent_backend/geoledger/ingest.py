"""
From material to ledger: extract candidates, resolve each to an asset (match, else mint an approximate one), append the
status events, and remember what was read so no stored text is ever paid for twice.

    ingest(ledger, material, ask)      one material; returns a report and the event rows (for the daily's section)
    attach(sections, ask, as_of)       the daily's additive step: ``section["asset_events"]``; never raises
    add_event(...)                     the dated, sourced, claimant-required write path agents and the CLI use

Failure is local: a failed call is reported and retried by the next run (it is not marked read); a candidate that cannot
be placed still becomes an unplaced asset with its event, because "who said what about which named thing" is useful
before anyone knows where it is.
"""

from __future__ import annotations

import json
from collections.abc import Callable
from datetime import date
from typing import Any

from . import extract as ex
from . import flags, match, publish
from .contracts import NOTE_CHARS, Asset, StatusEvent, event_id, fold, new_asset_id, valid_day
from .materials import Material, from_section
from .store import Ledger, now_iso

IsoAt = Callable[[float, float], str]


def _valid_country(code: str) -> bool:
    try:
        from algent_backend.actors import registry

        return code in registry.load()
    except Exception:  # noqa: BLE001 - without the registry any two-letter code passes
        return len(code) == 2


# -- the read-once memory --------------------------------------------------------------------------
def _seen_path(ledger: Ledger):
    return ledger.base / "extracted.jsonl"


def seen_keys(ledger: Ledger) -> set[str]:
    try:
        return {json.loads(x)["key"] for x in _seen_path(ledger).read_text(encoding="utf-8").splitlines() if x.strip()}
    except (OSError, ValueError, KeyError):
        return set()


def _mark_seen(ledger: Ledger, m: Material, report: dict) -> None:
    _seen_path(ledger).parent.mkdir(parents=True, exist_ok=True)
    with _seen_path(ledger).open("a", encoding="utf-8", newline="\n") as f:
        f.write(json.dumps({"key": m.key, "via": m.via, "at": now_iso(), "events": report["events"]}) + "\n")


# -- resolution ------------------------------------------------------------------------------------
def resolve(ledger: Ledger, c: ex.Candidate, m: Material) -> tuple[Asset, bool]:
    """The asset a candidate is about, and whether it was newly minted (an existing asset may gain an alias)."""
    at = (c.lat, c.lon) if c.lat is not None and c.lon is not None else None
    hit = match.find(ledger, [c.name, c.known_as], type_=c.type, country=c.country, at=at)
    if hit.asset is not None:
        a = hit.asset
        known = {fold(x) for x in (a.name, *a.aliases)}
        extra = [n for n in (c.name, c.known_as) if n and fold(n) not in known]
        if extra:
            a = a.model_copy(update={"aliases": [*a.aliases, *extra][:8]})
            ledger.add_assets([a])
        return a, False
    name = c.known_as or c.name
    a = Asset(id=new_asset_id(name, c.type, c.country), name=name, aliases=[c.name] if c.known_as and fold(c.known_as) != fold(c.name) else [],
              type=c.type, country=c.country, lat=c.lat, lon=c.lon,                  # type: ignore[arg-type]
              precision="approximate" if at else "unplaced", attrs={"place": c.place} if c.place else {},
              source=f"Ohmega extraction from: {m.label}"[:160], licence="Ohmega", provenance="ohmega_derived")
    prior = ledger.assets.get(a.id)
    if prior is not None:                                   # the same facility named the same way, seen before
        return prior, False
    ledger.add_assets([a])
    return a, True


def event_row(ledger: Ledger, a: Asset, e: StatusEvent) -> dict:
    return {"asset_id": a.id, "name": a.name, "type": a.type, "country": a.country, "lat": a.lat, "lon": a.lon,
            "status": e.status, "claimant": e.claimant, "confidence": e.confidence, "date": e.occurred_on,
            "sources": e.sources, "note": e.note, "provenance": e.provenance}


def ingest(ledger: Ledger, m: Material, ask: Callable[[Any, str, str], Any], *, today: date | None = None,
           iso_at: IsoAt | None = None, force: bool = False) -> dict[str, Any]:
    """Read one material into the ledger. Report: calls, candidates, created, events (new), rows (every event the
    material states, new or already known, for display), notes, error. Never raises."""
    report: dict[str, Any] = {"via": m.via, "calls": 0, "candidates": 0, "created": 0, "events": 0, "rows": [], "notes": [], "error": ""}
    if not m.items or (not force and m.key in seen_keys(ledger)):
        report["skipped"] = "nothing to read" if not m.items else "already read"
        report["rows"] = [event_row(ledger, ledger.assets[e.asset_id], e) for e in ledger.events.values() if e.via == m.via]
        return report
    try:
        cands, notes, report["calls"] = ex.extract(m, ask, today=today, iso_at=iso_at, valid_country=_valid_country)
        report["notes"] = notes
        report["candidates"] = len(cands)
        new_events: list[StatusEvent] = []
        for c in cands:
            a, created = resolve(ledger, c, m)
            report["created"] += created
            e = StatusEvent(id=event_id(a.id, c.occurred_on, c.status, c.claimant), asset_id=a.id, occurred_on=c.occurred_on,
                            occurred_at=c.occurred_at, status=c.status, claimant=c.claimant, confidence=c.confidence,   # type: ignore[arg-type]
                            sources=c.sources, provenance="ohmega_derived" if fold(c.claimant).startswith("ohmega") else "aggregated",
                            note=c.note[:NOTE_CHARS], via=m.via)
            new_events.append(e)
            report["rows"].append(event_row(ledger, a, e))
        report["events"] = ledger.add_events(new_events)
        _mark_seen(ledger, m, report)
    except Exception as exc:  # noqa: BLE001 - extraction is an addition to the day, never its gate
        report["error"] = f"{type(exc).__name__}: {str(exc)[:160]}"
    return report


# -- the write path for agents and the CLI ---------------------------------------------------------
def add_event(ledger: Ledger, asset_id: str, *, status: str, claimant: str, occurred_on: str, sources: list[str],
              confidence: str = "medium", note: str = "", occurred_at: str = "", via: str = "cli") -> StatusEvent:
    """Record one status event by hand. Dated, sourced, and the claimant named, or it is refused with a ValueError."""
    from .contracts import STATUSES

    if asset_id not in ledger.assets:
        raise ValueError(f"unknown asset {asset_id!r}")
    if status not in STATUSES:
        raise ValueError(f"status must be one of: {', '.join(STATUSES)}")
    if not claimant.strip():
        raise ValueError("a claimant is required: who says it (a status is always somebody's word)")
    if not valid_day(occurred_on):
        raise ValueError("occurred_on must be a date, YYYY-MM-DD")
    urls = [u for u in sources if u.startswith(("http://", "https://"))]
    if not urls:
        raise ValueError("at least one source url (http/https) is required")
    if confidence not in ("low", "medium", "high"):
        raise ValueError("confidence must be low, medium or high")
    e = StatusEvent(id=event_id(asset_id, occurred_on, status, claimant), asset_id=asset_id, occurred_on=occurred_on,
                    occurred_at=occurred_at, status=status, claimant=" ".join(claimant.split()), confidence=confidence,   # type: ignore[arg-type]
                    sources=urls, provenance="ohmega_derived" if fold(claimant).startswith("ohmega") else "aggregated",
                    note=note[:NOTE_CHARS], via=via)
    ledger.add_events([e])
    return e


# -- the daily's additive step ---------------------------------------------------------------------
def attach(sections: list[dict], *, ask: Callable[[Any, str, str], Any], as_of: str, ledger: Ledger | None = None,
           iso_at: IsoAt | None = None, publish_now: bool = True) -> dict | None:
    """For each section: read its developments into the ledger and set ``section["asset_events"]`` to the events they
    state. Returns a small report for the record (None when switched off). Never raises, never gates the day."""
    if not flags.ENABLED or not sections:
        return None
    try:
        ledger = ledger or Ledger()
        iso_at = iso_at if iso_at is not None else _default_iso_at()
        report: dict[str, Any] = {"calls": 0, "events": 0, "created": 0, "errors": [], "notes": []}
        for s in sections:
            r = ingest(ledger, from_section(s, as_of), ask, today=date.fromisoformat(as_of), iso_at=iso_at)
            report["calls"] += r["calls"]
            report["events"] += r["events"]
            report["created"] += r["created"]
            report["notes"] += [f"{s.get('theater_id', '?')}: {n}" for n in r["notes"][:4]]
            if r["error"]:
                report["errors"].append(f"{s.get('theater_id', '?')}: {r['error']}")
            if r["rows"]:
                s["asset_events"] = r["rows"]
        if publish_now and report["events"]:
            report["published"] = publish.publish(ledger).get("db", False)
        return report
    except Exception as exc:  # noqa: BLE001
        return {"calls": 0, "events": 0, "errors": [f"{type(exc).__name__}: {str(exc)[:160]}"]}


def _default_iso_at() -> IsoAt:
    from .seed_osm import default_iso_at

    return default_iso_at()
