"""
Pulse rescue - rebuild a lost stretch of the Pulse ledger from what the live site still served (``newsroom pulse rebuild``).

The Postgres Pulse ledger (2026-10-09 .. 10-21) is probably lost with the database, and the server's file store stops at 10-09. Two honest
sources remain, and they are merged into the FILE store (the system of record) without ever overwriting an entry:

(a) **rescued readings.** The published ``pulse_<id>.json`` documents (``ohmega.pulse/1``) carry every reading the site showed, with its
    original timestamp, position, decision, confidence and reader-safe rationale. Each reading the store does not already have becomes an
    influence marked ``provenance: rescued_from_site_cache``. (The rationale is the reader-safe text the site published, not the original.)
(b) **reconstructed readings.** For the days AFTER a Pulse's last rescued/known reading, the daily reports (``intel_store/daily/<domain>/*.json``)
    list per section the Pulses it bears on with their positions. One position reading per Pulse per day is rebuilt from them, marked
    ``provenance: reconstructed_from_daily``. It has NO assessment rationale and says so in its own text; it carries a low confidence.

Idempotent: every written influence has a deterministic key and an existing key or an existing reading of the same timestamp/day is skipped.
Dry run reports the counts and writes nothing. Nothing is ever deleted or edited.
"""

from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .contracts import Confidence, Influence, Pulse, PulseDefinition, Situation, Source
from .store import DuplicateInfluence

RESCUED = "rescued_from_site_cache"
RECONSTRUCTED = "reconstructed_from_daily"
_MODE = {"seed": "seed", "article": "article", "reassessment": "reassess", "reassess": "reassess", "audit": "blind", "blind": "blind"}
_NOTE = "Reconstructed from the published daily report of {day}: the position only. No assessment rationale was recorded for this reading."


def _key(tag: str, *parts: str) -> str:
    return f"inf_{tag}_" + hashlib.sha1("|".join(parts).encode("utf-8")).hexdigest()[:14]


def _ts(text: str) -> datetime:
    dt = datetime.fromisoformat(text.replace("Z", "+00:00"))
    return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)


def _load(path: Path) -> dict[str, Any] | None:
    try:
        doc = json.loads(path.read_text(encoding="utf-8"))
        return doc if isinstance(doc, dict) else None
    except (OSError, ValueError):
        return None


def _confidence(level: str) -> Confidence:
    level = level if level in ("high", "medium", "low") else "medium"
    return Confidence(evidence_quality=level, coverage=level, note="as published on the site")


def _ensure_pulse(store: Any, doc: dict[str, Any], dry_run: bool) -> tuple[Pulse | None, bool]:
    """The Pulse of a rescued document: the store's own when present, else created from the published definition. (pulse, created)."""
    pid = str(doc.get("id", ""))
    have = store.pulse(pid)
    if have is not None or not pid:
        return have, False
    d = doc.get("definition") or {}
    pulse = Pulse(id=pid, situation_id=str(doc.get("situation_id", "")), name=str(doc.get("name", pid)),
                  status=doc.get("status") if doc.get("status") in ("experimental", "active", "dormant") else "experimental",
                  definitions=[PulseDefinition(question=str(d.get("question", "")), low_end=str(d.get("low_end", "")),
                                               high_end=str(d.get("high_end", "")), note="recreated from the published Pulse document")])
    if dry_run:
        return pulse, True
    if pulse.situation_id and store.situation(pulse.situation_id) is None:
        store.save_situation(Situation(id=pulse.situation_id, title=str(doc.get("situation") or pulse.situation_id)))
    store.create_pulse(pulse)
    return store.pulse(pid), True


def _append(store: Any, influence: Influence, dry_run: bool) -> bool:
    if dry_run:
        return True
    try:
        store.append(influence)
        return True
    except DuplicateInfluence:
        return False


def rescue_readings(store: Any, rescue_dir: Path, *, dry_run: bool) -> dict[str, Any]:
    out = {"pulses_seen": 0, "pulses_created": 0, "readings_added": 0, "readings_present": 0, "last_reading": {}}
    for path in sorted(rescue_dir.glob("pulse_*.json")):
        doc = _load(path)
        if not doc or doc.get("schema") != "ohmega.pulse/1":
            continue
        out["pulses_seen"] += 1
        pulse, created = _ensure_pulse(store, doc, dry_run)
        out["pulses_created"] += created
        if pulse is None:
            continue
        pid = pulse.id
        known = {_ts(i.at).isoformat() for i in store.log(pid)} if store.pulse(pid) is not None else set()
        version = pulse.definition.version
        for r in doc.get("readings") or []:
            at = str(r.get("at", ""))
            if not at:
                continue
            stamp = _ts(at).isoformat()
            out["last_reading"][pid] = max(out["last_reading"].get(pid, ""), stamp)
            if stamp in known:
                out["readings_present"] += 1
                continue
            slug = str(r.get("article_url") or "").removeprefix("/articles/")
            decision = r.get("decision") if r.get("decision") in ("applied", "no_change", "rejected", "reconcile") else "no_change"
            inf = Influence(key=_key("rescue", pid, stamp, str(r.get("mode", ""))), pulse_id=pid, at=at, evidence_through=str(r.get("evidence_through", "")),
                            mode=_MODE.get(str(r.get("mode", "")), "reassess"), definition_version=version,
                            proposed_position=r.get("position") if isinstance(r.get("position"), (int, float)) else None, decision=decision,
                            rationale=str(r.get("rationale", "")), confidence=_confidence(str(r.get("confidence", ""))),
                            source=Source(stage="pulse_rescue", article_slug=slug), model=str(r.get("model", "")), provenance=RESCUED)
            if _append(store, inf, dry_run):
                out["readings_added"] += 1
            else:
                out["readings_present"] += 1
    return out


def daily_positions(dailies_dir: Path) -> dict[str, dict[str, dict[str, Any]]]:
    """``{pulse id: {day: {position, at}}}`` from the daily reports under ``dailies_dir/<domain>/<date>.json`` (the latest report of a day wins)."""
    out: dict[str, dict[str, dict[str, Any]]] = {}
    for path in sorted(dailies_dir.glob("*/*.json")):
        rec = _load(path)
        if not rec:
            continue
        day = path.stem[:10]
        at = str(rec.get("built_at") or f"{day}T12:00:00+00:00")
        for sec in rec.get("theaters") or rec.get("sections") or []:
            for p in (sec.get("pulses") or []) if isinstance(sec, dict) else []:
                if isinstance(p, dict) and p.get("id") and isinstance(p.get("position"), (int, float)):
                    cur = out.setdefault(str(p["id"]), {}).get(day)
                    if cur is None or at >= cur["at"]:
                        out[str(p["id"])][day] = {"position": float(p["position"]), "at": at}
    return out


def reconstruct(store: Any, dailies_dir: Path, last_reading: dict[str, str], *, dry_run: bool) -> dict[str, Any]:
    """One position reading per Pulse per day after its last known reading, from the dailies."""
    out = {"readings_added": 0, "pulses": 0, "days": 0}
    for pid, days in sorted(daily_positions(dailies_dir).items()):
        pulse = store.pulse(pid)
        if pulse is None:
            continue
        log = store.log(pid)
        # "after the last known reading": the last rescued one when the site's document had this Pulse, else the last in the store; a day that
        # already has ANY reading (a native one resumed later) is skipped on its own, so the days between are still filled.
        last = _ts(last_reading[pid]) if pid in last_reading else max((_ts(i.at) for i in log), default=None)
        have_days = {_ts(i.at).date().isoformat() for i in log}
        added = 0
        for day, obs in sorted(days.items()):
            if (last is not None and day <= last.date().isoformat()) or day in have_days:
                continue
            inf = Influence(key=_key("recon", pid, day), pulse_id=pid, at=obs["at"], evidence_through=day, mode="reassess",
                            definition_version=pulse.definition.version, proposed_position=obs["position"], decision="applied",
                            rationale=_NOTE.format(day=day), confidence=Confidence(evidence_quality="low", coverage="low", note=_NOTE.format(day=day)),
                            source=Source(stage="pulse_reconstruction"), provenance=RECONSTRUCTED)
            if _append(store, inf, dry_run):
                added += 1
        if added:
            out["pulses"] += 1
            out["days"] += added
        out["readings_added"] += added
    return out


def rebuild(store: Any, rescue_dir: Path, dailies_dir: Path | None = None, *, dry_run: bool = False) -> dict[str, Any]:
    """Merge the rescue into ``store``. Returns the report; the caller republishes the Pulse documents when ``readings_added`` > 0."""
    report: dict[str, Any] = {"dry_run": dry_run, "rescue_dir": str(rescue_dir)}
    if not rescue_dir.is_dir():
        return {**report, "error": f"{rescue_dir} is not a directory"}
    rescued = rescue_readings(store, rescue_dir, dry_run=dry_run)
    report["rescued"] = {k: v for k, v in rescued.items() if k != "last_reading"}
    if dailies_dir is not None and dailies_dir.is_dir():
        report["reconstructed"] = reconstruct(store, dailies_dir, rescued["last_reading"], dry_run=dry_run)
        report["reconstructed"]["note"] = "position only, provenance reconstructed_from_daily, no assessment rationale"
    else:
        report["reconstructed"] = {"skipped": "no dailies directory"}
    return report
