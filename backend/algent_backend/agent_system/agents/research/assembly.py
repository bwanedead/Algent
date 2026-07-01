"""
Profile assembly — the harness step that turns model-authored items into a robust,
graph-ready stored object (and folds enricher additions into an existing profile).

The model writes with simple LOCAL ids (s1/c1/e1/t1); this code makes it sound:
- assigns STABLE ids: content-addressed for sources (normalized URL) and entities
  (canonical name + type) — the cross-profile join-keys; content-hash for claims/threads;
- REWRITES every reference through the local->stable map, dropping dangling refs;
- DEDUPES items that collapse to the same id (so re-adding is idempotent — the basis of merge);
- attaches harness-captured SNAPSHOTS by normalized URL (sole authority — a model can't hash;
  on merge, already-verified snapshots are preserved);
- computes GROUNDING (a claim is "snapshotted" only if a deep-read source backs it; a thread
  inherits the weakest of its claims);
- stamps per-item + profile PROVENANCE.

Two entry points share one core (``_assemble``): ``finalize_profile`` (first build) and
``merge_additions`` (fold an enricher's additions, revision++). Pure — no I/O.
"""

from __future__ import annotations

import hashlib
import re
from datetime import UTC, datetime
from typing import Any

from .grounding import cap_status_by_grounding
from .profile import (
    SCHEMA_VERSION,
    ItemProvenance,
    ProfileAdditions,
    SignalProfile,
    SourceSnapshot,
)

_GROUNDING_ORDER = {"snapshotted": 0, "snippet_only": 1, "unsourced": 2}


def finalize_profile(
    profile: SignalProfile, vector: dict[str, Any], captured: dict[str, dict],
    *, model: str, generator: str, stage: str,
) -> SignalProfile:
    """First build: assemble the model's items, stamp the profile id + provenance."""
    revision = profile.revision or 1
    prov = ItemProvenance(added_by_stage=stage, revision=revision, created_at=_now())
    # First build: the harness is the sole snapshot authority — discard all model snapshots
    # so only real captured ones survive.
    for s in profile.source_ledger:
        s.snapshot = None
    sources, entities, claims, threads = _assemble(
        profile.source_ledger, profile.entities, profile.claim_ledger, profile.threads, captured, prov
    )
    return profile.model_copy(update={
        "id": _profile_id(vector),
        "parent_vector_id": vector.get("id", ""),
        "source_ledger": sources, "claim_ledger": claims, "entities": entities, "threads": threads,
        # Deterministic floor: the model may not claim maturity while a load-bearing claim/thread
        # is only snippet-grounded (see grounding.py).
        "profile_status": cap_status_by_grounding(profile.profile_status, claims, threads),
        "revision": revision, "schema_version": SCHEMA_VERSION,
        "generated_at": prov.created_at, "generator": generator, "model": model,
    })


def merge_additions(
    profile: SignalProfile, additions: ProfileAdditions, captured: dict[str, dict],
    *, generator: str, stage: str,
) -> SignalProfile:
    """Fold an enricher's additive items into an existing profile (revision++).

    Existing items keep their stable ids (content-addressing is idempotent) and their
    already-verified snapshots; new items get stable ids, snapshots from THIS run's reads,
    and provenance stamped with the new revision + the enricher stage. Dedup collapses any
    overlap. Meta lists are appended; status becomes 'enriching'.
    """
    new_rev = (profile.revision or 1) + 1
    prov = ItemProvenance(added_by_stage=stage, revision=new_rev, created_at=_now())
    # The enricher's additions are model-authored: clear their snapshots (harness re-attaches
    # real captures) and provenance (harness stamps this revision/stage) so existing items keep
    # their verified snapshots + original provenance while new items are correctly attributed.
    for s in additions.sources:
        s.snapshot = None
    # Entities are lightweight nodes with no provenance field; only these carry it.
    for item in (*additions.sources, *additions.claims, *additions.threads):
        item.provenance = None
    sources, entities, claims, threads = _assemble(
        profile.source_ledger + additions.sources,
        profile.entities + additions.entities,
        profile.claim_ledger + additions.claims,
        profile.threads + additions.threads,
        captured, prov,
    )
    return profile.model_copy(update={
        "source_ledger": sources, "claim_ledger": claims, "entities": entities, "threads": threads,
        "revision": new_rev, "schema_version": SCHEMA_VERSION, "profile_status": "enriching",
        "omissions": _dedup_strs(profile.omissions + additions.omissions),
        "open_questions": _dedup_strs(profile.open_questions + additions.open_questions),
    })


def _place_sources(source_ledger, captured_norm, prov):
    """Assign content-addressed ids, dedup, and attach real captures (keeping verified snapshots)."""
    src_map: dict[str, str] = {}
    sources, seen_src = [], set()
    for s in source_ledger:
        new = _source_id(s)
        src_map[s.id] = new
        if new in seen_src:
            continue
        s.id = new
        if s.snapshot is None:  # keep an already-verified snapshot; else attach a real capture
            snap = captured_norm.get(_norm_url(s.url)) if s.url else None
            s.snapshot = SourceSnapshot(**snap) if snap else None
        s.provenance = s.provenance or prov
        seen_src.add(new)
        sources.append(s)
    return sources, src_map


def _assemble(source_ledger, entities_in, claim_ledger, threads_in, captured, prov):
    """The shared core: ids, refs, dedup, snapshots, grounding, provenance."""
    captured_norm = {_norm_url(u): v for u, v in captured.items()}
    sources, src_map = _place_sources(source_ledger, captured_norm, prov)

    ent_map: dict[str, str] = {}
    entities, seen_ent = [], set()
    for e in entities_in:
        if not e.canonical_name:
            e.canonical_name = e.name
        new = _entity_id(e)
        ent_map[e.id] = new
        if new in seen_ent:
            continue
        e.id = new
        seen_ent.add(new)
        entities.append(e)

    snapshotted = {s.id for s in sources if s.snapshot is not None}
    claim_map: dict[str, str] = {}
    claims, seen_clm = [], {}
    for c in claim_ledger:
        new = _claim_id(c)
        claim_map[c.id] = new
        if new in seen_clm:
            continue
        c.id = new
        c.supported_by = _remap(c.supported_by, src_map)
        c.contradicted_by = _remap(c.contradicted_by, src_map)
        c.grounding = _claim_grounding(c.supported_by, snapshotted)
        c.provenance = c.provenance or prov
        seen_clm[new] = c
        claims.append(c)

    threads, seen_thr = [], set()
    for t in threads_in:
        new = _thread_id(t)
        if new in seen_thr:
            continue
        t.id = new
        t.entities = _remap(t.entities, ent_map)
        t.claims = _remap(t.claims, claim_map)
        t.sources = _remap(t.sources, src_map)
        t.grounding = _thread_grounding(t.claims, seen_clm)
        t.provenance = t.provenance or prov
        seen_thr.add(new)
        threads.append(t)

    return sources, entities, claims, threads


def _claim_grounding(supported_by: list[str], snapshotted: set[str]) -> str:
    if not supported_by:
        return "unsourced"
    return "snapshotted" if any(s in snapshotted for s in supported_by) else "snippet_only"


def _thread_grounding(claim_ids: list[str], claims_by_id: dict[str, Any]) -> str:
    levels = [claims_by_id[c].grounding for c in claim_ids if c in claims_by_id]
    if not levels:
        return "unsourced"
    return max(levels, key=lambda g: _GROUNDING_ORDER.get(g, 2))


def _remap(refs: list[str], mapping: dict[str, str]) -> list[str]:
    out: list[str] = []
    for ref in refs:
        stable = mapping.get(ref)
        if stable and stable not in out:
            out.append(stable)
    return out


def _dedup_strs(items: list[str]) -> list[str]:
    out: list[str] = []
    for s in items:
        if s and s not in out:
            out.append(s)
    return out


def _norm_url(url: str) -> str:
    u = url.strip().lower()
    u = re.sub(r"^https?://", "", u)
    u = re.sub(r"^www\.", "", u)
    return u.split("#")[0].rstrip("/")


def _hash(text: str, prefix: str, n: int = 10) -> str:
    return prefix + hashlib.sha1(text.encode("utf-8")).hexdigest()[:n]


def _source_id(source: Any) -> str:
    key = _norm_url(source.url) or source.title.strip().lower() or source.id
    return _hash(key, "src_")


def _entity_id(entity: Any) -> str:
    name = (entity.canonical_name or entity.name).strip().lower()
    return _hash(f"{name}|{entity.type}", "ent_")


def _claim_id(claim: Any) -> str:
    return _hash(re.sub(r"\s+", " ", claim.text.strip().lower()), "clm_")


def _thread_id(thread: Any) -> str:
    return _hash((thread.title + "|" + thread.body).strip().lower(), "thr_")


def _profile_id(vector: dict[str, Any]) -> str:
    vid = str(vector.get("id") or "")
    return "prof_" + (vid.removeprefix("vec_") or "unknown")


def _now() -> str:
    return datetime.now(UTC).isoformat()
