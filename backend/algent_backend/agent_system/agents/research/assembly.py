"""
Profile assembly — the harness step that turns a model-authored profile into a robust,
graph-ready stored object.

The model writes with simple LOCAL ids (s1, c1, e1, t1) and links between them — easy to
keep internally consistent. This code makes it sound:
- assigns STABLE ids: content-addressed for sources (normalized URL) and entities
  (canonical name + type) — the cross-profile join-keys; content-hash for claims/threads;
- REWRITES every reference through the local->stable map, dropping any dangling ref;
- DEDUPES sources/entities/claims/threads that collapse to the same id;
- attaches harness-captured SNAPSHOTS by URL (the harness is the sole authority — a model
  can't hash);
- stamps per-item + profile PROVENANCE and the profile's stable id.

Same principle as snapshots and vector ids: the model reasons, the harness guarantees
integrity. Pure functions — no I/O, easy to test.
"""

from __future__ import annotations

import hashlib
import re
from datetime import UTC, datetime
from typing import Any

from .profile import ItemProvenance, SignalProfile, SourceSnapshot


def finalize_profile(
    profile: SignalProfile,
    vector: dict[str, Any],
    captured: dict[str, dict],
    *,
    model: str,
    generator: str,
    stage: str,
) -> SignalProfile:
    """Assign stable ids, rewrite refs, dedup, attach snapshots, stamp provenance."""
    revision = profile.revision or 1
    prov = ItemProvenance(added_by_stage=stage, revision=revision, created_at=_now())
    # Normalize captured snapshot keys so a model-written url matches the read-tool url
    # despite scheme/www/trailing-slash/case differences.
    captured_norm = {_norm_url(u): v for u, v in captured.items()}

    # 1. Sources — content-addressed id, dedup, harness snapshot, provenance.
    src_map: dict[str, str] = {}
    sources, seen_src = [], set()
    for s in profile.source_ledger:
        new = _source_id(s)
        src_map[s.id] = new
        if new in seen_src:
            continue
        s.id = new
        captured_snap = captured_norm.get(_norm_url(s.url)) if s.url else None
        s.snapshot = SourceSnapshot(**captured_snap) if captured_snap else None
        s.provenance = s.provenance or prov
        seen_src.add(new)
        sources.append(s)

    # 2. Entities — content-addressed id (canonical name + type), dedup.
    ent_map: dict[str, str] = {}
    entities, seen_ent = [], set()
    for e in profile.entities:
        if not e.canonical_name:
            e.canonical_name = e.name
        new = _entity_id(e)
        ent_map[e.id] = new
        if new in seen_ent:
            continue
        e.id = new
        seen_ent.add(new)
        entities.append(e)

    # 3. Claims — content-hash id, rewrite source refs (drop dangling), dedup.
    claim_map: dict[str, str] = {}
    claims, seen_clm = [], set()
    for c in profile.claim_ledger:
        new = _claim_id(c)
        claim_map[c.id] = new
        if new in seen_clm:
            continue
        c.id = new
        c.supported_by = _remap(c.supported_by, src_map)
        c.contradicted_by = _remap(c.contradicted_by, src_map)
        c.provenance = c.provenance or prov
        seen_clm.add(new)
        claims.append(c)

    # 4. Threads — id, rewrite entity/claim/source refs, dedup.
    threads, seen_thr = [], set()
    for t in profile.threads:
        new = _thread_id(t)
        if new in seen_thr:
            continue
        t.id = new
        t.entities = _remap(t.entities, ent_map)
        t.claims = _remap(t.claims, claim_map)
        t.sources = _remap(t.sources, src_map)
        t.provenance = t.provenance or prov
        seen_thr.add(new)
        threads.append(t)

    return profile.model_copy(update={
        "id": _profile_id(vector),
        "parent_vector_id": vector.get("id", ""),
        "source_ledger": sources,
        "claim_ledger": claims,
        "entities": entities,
        "threads": threads,
        "revision": revision,
        "generated_at": prov.created_at,
        "generator": generator,
        "model": model,
    })


def _remap(refs: list[str], mapping: dict[str, str]) -> list[str]:
    """Rewrite local refs to stable ids; drop any that don't resolve; dedup, keep order."""
    out: list[str] = []
    for ref in refs:
        stable = mapping.get(ref)
        if stable and stable not in out:
            out.append(stable)
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
