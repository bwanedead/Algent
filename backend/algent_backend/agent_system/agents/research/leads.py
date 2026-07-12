"""
The backfeed loop — any pipeline stage's derived leads flow back to the t0 discovery pool.

When research (or later the drafter, reviewers) notices an adjacent story worth its own vector, it
records a ``DerivedLead``. This is the store + mechanism that carries those leads back to discovery
so the newsroom crowdsources its own organic ideas — with three guardrails baked in (per review):

- DEDUP: leads are content-addressed (same story -> same id, collapses re-emissions), and a lead
  already covered by an existing profile is skipped, so the loop never double-researches its output.
  (A cheap check now; the deferred corpus-dedup becomes the real answer as this scales.)
- PROVENANCE: every backfed lead keeps ``lead_origin`` + ``created_by_stage`` so discovery can weight
  and audit organic-vs-derived.
- DAMPING: consumption is capped per run, so research-spawns-leads-spawns-research can't self-amplify.

Backfed leads are CANDIDATES to be judged by the next discovery synthesis — never pre-vetted.
"""

from __future__ import annotations

import hashlib
import os
import re
from pathlib import Path
from typing import Protocol

from .profile import DerivedLead, SignalProfile

_STORE_ENV = "ALGENT_LEAD_STORE"
_DEFAULT_DIR = "lead_store"
_DEFAULT_PROMOTE_CAP = 5  # damping: at most this many backfed leads enter one discovery run


def _norm(text: str) -> str:
    return re.sub(r"\s+", " ", (text or "").strip().lower())


def lead_id(lead: DerivedLead) -> str:
    """Content-addressed: same story (title + source) -> same id, so re-emissions collapse."""
    key = f"{_norm(lead.title)}|{_norm(lead.source_url)}"
    return "lead_" + hashlib.sha1(key.encode("utf-8")).hexdigest()[:10]


def _safe(name: str) -> str:
    return re.sub(r"[^A-Za-z0-9._-]+", "_", name) or "lead"


class LeadStore(Protocol):
    def save(self, lead: DerivedLead) -> str: ...
    def list_open(self) -> list[DerivedLead]: ...
    def mark_consumed(self, lead_id: str) -> None: ...


class JsonLeadStore:
    """File-backed backfeed queue: open leads as ``<id>.json``; consumed ones move to ``consumed/``."""

    def __init__(self, base_dir: Path | str | None = None) -> None:
        self._dir = Path(base_dir or os.environ.get(_STORE_ENV) or _DEFAULT_DIR)

    def save(self, lead: DerivedLead) -> str:
        self._dir.mkdir(parents=True, exist_ok=True)
        path = self._dir / f"{_safe(lead.id)}.json"
        # Content-addressed id means a re-emitted lead simply overwrites its twin (idempotent dedup).
        if not (self._dir / "consumed" / path.name).exists():  # don't resurrect a consumed lead
            path.write_text(lead.model_dump_json(indent=2), encoding="utf-8")
        return str(path)

    def list_open(self) -> list[DerivedLead]:
        if not self._dir.exists():
            return []
        out = []
        for p in self._dir.glob("*.json"):
            try:
                out.append(DerivedLead.model_validate_json(p.read_text(encoding="utf-8")))
            except Exception:  # noqa: BLE001 — a bad file must not break discovery
                continue
        return out

    def mark_consumed(self, lead_id: str) -> None:
        src = self._dir / f"{_safe(lead_id)}.json"
        if src.exists():
            dst = self._dir / "consumed"
            dst.mkdir(parents=True, exist_ok=True)
            src.replace(dst / src.name)


def backfeed_leads(leads: list[DerivedLead], *, stage: str, store: LeadStore) -> list[str]:
    """Fold a stage's derived leads into the backfeed queue: content-address, stamp provenance, dedup.
    Returns the ids saved. Guarded — a store hiccup must never fail the producing run."""
    saved = []
    for lead in leads:
        stamped = lead.model_copy(update={
            "id": lead_id(lead),
            "lead_origin": lead.lead_origin or "research_backfeed",
            "created_by_stage": lead.created_by_stage or stage,
        })
        try:
            store.save(stamped)
            saved.append(stamped.id)
        except Exception:  # noqa: BLE001
            pass
    return saved


def is_covered(lead: DerivedLead, profiles: list[SignalProfile]) -> bool:
    """Cheap dedup-against-corpus: a lead whose entities substantially overlap an existing profile's
    is likely already researched — skip it. (Placeholder for real corpus-dedup / retrieval later.)"""
    lead_ents = {_norm(e) for e in lead.entities if e}
    if not lead_ents:
        return False
    for p in profiles:
        prof_ents = {_norm(e.name) for e in p.entities} | {_norm(e.canonical_name) for e in p.entities}
        overlap = lead_ents & prof_ents
        if len(overlap) >= 2 or (lead_ents and overlap == lead_ents):
            return True
    return False


def open_leads_for_discovery(
    store: LeadStore, *, limit: int = _DEFAULT_PROMOTE_CAP, profiles: list[SignalProfile] | None = None
) -> list[DerivedLead]:
    """The damped, deduped candidates the next discovery run should consider (never pre-vetted).
    Higher-confidence leads first; those already covered by an existing profile are dropped."""
    leads = store.list_open()
    if profiles:
        leads = [le for le in leads if not is_covered(le, profiles)]
    order = {"high": 0, "med": 1, "medium": 1, "low": 2, "": 3}
    leads.sort(key=lambda le: order.get(_norm(le.confidence), 3))
    return leads[:max(0, limit)]
