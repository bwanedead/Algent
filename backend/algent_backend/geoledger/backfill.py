"""
Backfill: read the texts we already hold (saved dailies, research profiles, the statements ledger, library articles)
into the ledger, newest window first. No new research and no fetching; each stored text is read at most once, ever
(``ingest`` remembers the fingerprint), so a rerun, or an overlap with the daily's own step, costs nothing.

Library articles are numerous, so they pass a cheap, free gate first: a text must mention BOTH a kind of facility or
vessel and an act upon it before it is worth a model call. The gate only decides whether to spend; it never decides
what an event is (the model does, and the harness checks it).
"""

from __future__ import annotations

import json
import os
import re
from collections.abc import Callable, Iterator
from datetime import date, timedelta
from pathlib import Path
from typing import Any

from .ingest import ingest, seen_keys
from .materials import Material, from_document, from_profile, from_section, from_statements
from .store import Ledger

KINDS = ("daily", "profiles", "statements", "library")
_THING = re.compile(r"power (plant|station)|thermal|\bchp\b|\btpp\b|\bhpp\b|substation|refiner|oil depot|fuel depot|\bport\b|"
                    r"airbase|air base|airfield|\bdam\b|bridge|tanker|vessel|\bship\b|sanction|designat", re.I)
_ACT = re.compile(r"strik|struck|hit\b|attack|drone|missile|shell|damag|destroy|seiz|captur|blockad|sanction|designat|"
                  r"blacklist|outage|blackout|restor|repair", re.I)


def worth_reading(text: str) -> bool:
    return bool(_THING.search(text)) and bool(_ACT.search(text))


def intel_dir() -> Path:
    return Path(os.environ.get("ALGENT_INTEL_STORE") or "intel_store")


def _daily_materials(since: str, domain: str = "geopolitics") -> Iterator[Material]:
    folder = intel_dir() / "daily" / domain
    for path in sorted(folder.glob("*.json")) if folder.is_dir() else []:
        if path.stem < since:
            continue
        try:
            record = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            continue
        for sec in record.get("theaters") or []:
            for s in [sec, *(sec.get("updates") or [])]:
                yield from_section(s, path.stem)


def _profile_materials(since: str) -> Iterator[Material]:
    from algent_backend.agent_system.agents.research.store import JsonProfileStore

    store = JsonProfileStore()
    for pid in store.list_ids():
        p = store.get(pid)
        if p is not None and (p.as_of or "")[:10] >= since:
            yield from_profile(p)


def _statement_materials(since: str) -> Iterator[Material]:
    from algent_backend.agent_system.agents.statements import store

    rows = [s for s in store.load_statements() if s.date >= since]
    for k in range(0, len(rows), 25):
        yield from_statements(rows[k:k + 25])


def _library_materials(since: str) -> Iterator[Material]:
    from algent_backend.library import store

    conn = store.connect(create=False)
    if conn is None:
        return
    try:
        cur = conn.execute("select url, title, text, published, fetched_at from documents where latest = 1 "
                           "and substr(coalesce(nullif(published, ''), fetched_at), 1, 10) >= ? order by fetched_at desc", (since,))
        for r in cur:
            if worth_reading(f"{r['title']} {r['text']}"):
                yield from_document(r["url"], r["title"], r["text"], r["published"], r["fetched_at"])
    finally:
        conn.close()


_SOURCES: dict[str, Callable[[str], Iterator[Material]]] = {
    "daily": _daily_materials, "profiles": _profile_materials, "statements": _statement_materials, "library": _library_materials}


def plan(since: str, kinds: tuple[str, ...] = KINDS, ledger: Ledger | None = None) -> list[Material]:
    """The materials a backfill would read (unread ones only), without spending anything."""
    ledger = ledger or Ledger()
    done = seen_keys(ledger)
    return [m for k in kinds for m in _SOURCES[k](since) if m.items and m.key not in done]


def run(ledger: Ledger, ask: Callable[[Any, str, str], Any], since: str, kinds: tuple[str, ...] = KINDS, *,
        limit: int | None = None, force: bool = False) -> dict[str, Any]:
    """Read every unread stored text since ``since`` into the ledger. Returns totals and per-material problems."""
    todo = plan(since, kinds, ledger) if not force else [m for k in kinds for m in _SOURCES[k](since) if m.items]
    todo = todo[:limit] if limit else todo
    totals: dict[str, Any] = {"materials": len(todo), "calls": 0, "candidates": 0, "events": 0, "created": 0, "errors": [], "by_kind": {}}
    for m in todo:
        r = ingest(ledger, m, ask, today=date.today(), force=force)
        for k in ("calls", "candidates", "events", "created"):
            totals[k] += r[k]
        kind = m.via.split(":")[0]
        totals["by_kind"][kind] = totals["by_kind"].get(kind, 0) + r["events"]
        if r["error"]:
            totals["errors"].append(f"{m.via}: {r['error']}")
    return totals


def since_from_days(days: int, today: date | None = None) -> str:
    return ((today or date.today()) - timedelta(days=days)).isoformat()
