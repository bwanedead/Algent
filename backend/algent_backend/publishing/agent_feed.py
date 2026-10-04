"""
The agent feed builders — everything the site shows humans, as clean, citable, static JSON.

Pure functions: each returns ``{path relative to public/data: payload}``; ``intel_page.write_intel``
writes only the files whose content changed. The public contract (shapes, rules) is documented in
``intel_page.py``'s module docstring, which stays authoritative.

Rules enforced here: ``absolute_position`` is never read; internal workflow fields (``pulse_proposals``)
and claim ids never leave; every free-text rationale goes through ``reader_safe``; per-item files carry no
build timestamp, so an unchanged item is byte-identical and is not rewritten.
"""

from __future__ import annotations

import json
import re
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

from algent_backend.agent_system.agents.intel import forecasts
from algent_backend.agent_system.agents.intel.brief import safe_name

CHANGES_WINDOW_DAYS = 30
_MAX_RATIONALE = 400
_CLAIM_ID = re.compile(r"\bclm_[0-9a-f]+\b")
_MODE_WORDS = {"seed": "seed", "article": "article", "reassess": "reassessment", "blind": "audit"}
_INTERNAL_DAILY_FIELDS = ("pulse_proposals",)


def reader_safe(text: str, limit: int = _MAX_RATIONALE) -> str:
    """Strip internal claim ids (and the brackets/lists they leave empty), then trim at a word boundary."""
    out = _CLAIM_ID.sub("", text or "")
    out = re.sub(r"[\[(][\s,;]*[\])]", "", out)                  # brackets emptied by the strip
    out = re.sub(r"([\[(])[\s,;]+", r"\1", out)                  # separators left at the front
    out = re.sub(r"[\s,;]+([\])])", r"\1", out)                  # ...and at the back
    out = re.sub(r"([,;])(\s*[,;])+", r"\1", out)                # doubled separators in the middle
    out = re.sub(r"\s+([,.;:])", r"\1", out)
    out = " ".join(out.split())
    if len(out) <= limit:
        return out
    return out[:limit].rsplit(" ", 1)[0].rstrip(" ,;:-") + "…"


# ── urls (relative to the site root) ──────────────────────────────────────────────────────────
def daily_url(date: str) -> str:
    return f"/geopolitics/{date}"


def daily_data_url(domain: str, date: str) -> str:
    return f"/data/daily/{safe_name(domain)}/{date}.json"


def brief_url(slug: str) -> str:
    return f"/intel/briefs/{slug}"


def brief_data_url(slug: str) -> str:
    return f"/data/briefs/{slug}.json"


def pulse_data_url(pulse_id: str) -> str:
    return f"/data/pulses/{pulse_id}.json"


def _ts(value: str) -> datetime:
    """A stored timestamp or date as an aware UTC datetime (dates mean midnight UTC)."""
    dt = datetime.fromisoformat((value or "1970-01-01").replace("Z", "+00:00"))
    return dt if dt.tzinfo else dt.replace(tzinfo=UTC)


# ── daily reports and briefs ──────────────────────────────────────────────────────────────────
def public_daily(record: dict) -> dict:
    out = {k: v for k, v in record.items() if k not in _INTERNAL_DAILY_FIELDS}
    return {**out, "url": daily_url(record["date"]), "data_url": daily_data_url(record["domain"], record["date"])}


def public_brief(record: dict) -> dict:
    """The brief record, its judgments given the stable forecast id the ledger scores them under."""
    slug = record["slug"]
    out = {**record, "url": brief_url(slug), "data_url": brief_data_url(slug)}
    if "judgments" in record:
        out["judgments"] = [{"id": forecasts.forecast_id(slug, j.get("statement", "")), **j}
                            for j in record["judgments"] or [] if isinstance(j, dict)]
    return out


def daily_files(reports: list[dict]) -> dict[str, dict]:
    """Every dated report, plus ``latest.json`` per domain (the newest date; same content as that dated file)."""
    files: dict[str, dict] = {}
    newest: dict[str, dict] = {}
    for record in reports:                                       # newest first
        payload = public_daily(record)
        folder = safe_name(record["domain"])
        files[f"daily/{folder}/{record['date']}.json"] = payload
        newest.setdefault(folder, payload)
    files.update({f"daily/{folder}/latest.json": payload for folder, payload in newest.items()})
    return files


def brief_files(briefs: list[dict]) -> dict[str, dict]:
    return {f"briefs/{r['slug']}.json": public_brief(r) for r in briefs}


# ── forecasts ─────────────────────────────────────────────────────────────────────────────────
def _forecast_row(f: dict, brief: dict) -> dict:
    done = f["status"] != "open"
    return {"id": f["id"], "statement": f["statement"], "probability": f["probability"],
            "horizon": f["horizon"], "basis": f.get("basis", ""), "resolves_yes_if": f.get("resolves_yes_if", ""),
            "resolves_no_if": f.get("resolves_no_if", ""), "made_at": f["made_at"], "status": f["status"],
            "brief_slug": f["brief_slug"], "brief_url": brief_url(f["brief_slug"]),
            "brief_data_url": brief_data_url(f["brief_slug"]), "theater_id": f.get("theater_id", ""),
            "theater": brief.get("theater_name", ""),
            "resolution": {"resolved_at": f["resolved_at"], "outcome": f["status"], "evidence": f["evidence"]}
            if done else None}


def forecasts_file(intel_dir: Path, briefs: list[dict]) -> dict:
    by_slug = {b["slug"]: b for b in briefs}
    rows = sorted(forecasts.current(intel_dir), key=lambda f: (f["made_at"], f["id"]), reverse=True)
    stamps = [f["made_at"] for f in rows] + [f["resolved_at"] for f in rows if f["resolved_at"]]
    return {"schema": "ohmega.forecasts/1", "as_of": max(stamps, key=_ts) if stamps else "",
            "scorecard": forecasts.scorecard(intel_dir),
            "forecasts": [_forecast_row(f, by_slug.get(f["brief_slug"], {})) for f in rows]}


# ── pulse trace ───────────────────────────────────────────────────────────────────────────────
def _reading(i: Any) -> dict:
    """One log entry in public words. ``absolute_position``, prompt versions and claim/profile ids stay home."""
    slug = i.source.article_slug
    return {"at": i.at, "mode": _MODE_WORDS.get(i.mode, i.mode), "moves_pulse": i.mode != "blind",
            "decision": i.decision, "position": i.proposed_position, "rationale": reader_safe(i.rationale),
            "confidence": i.confidence.overall(), "evidence_through": i.evidence_through, "model": i.model,
            "article_url": f"/articles/{slug}" if slug else None}


def pulse_file(store: Any, row: dict, pulse: Any) -> dict:
    """The full trace of one Pulse: definition, where it stands, every reading. Blind reads are kept and
    labelled as audits (``mode: "audit"``, ``moves_pulse: false``) — provenance includes the checks."""
    log = sorted(store.log(pulse.id), key=lambda i: i.at)
    readings = [_reading(i) for i in log if i.decision in ("applied", "no_change") or i.mode == "blind"]
    d = pulse.definition
    keep = ("id", "name", "situation_id", "situation", "status", "position", "band", "confidence",
            "velocity_7d", "last_assessed", "evidence_through", "history")
    return {"schema": "ohmega.pulse/1", **{k: row[k] for k in keep},
            "definition": {"version": d.version, "question": d.question, "low_end": d.low_end,
                           "high_end": d.high_end},
            "url": "/pulses", "data_url": pulse_data_url(pulse.id), "readings": readings}


def pulse_files(store: Any, catalog: list[dict]) -> dict[str, dict]:
    return {f"pulses/{row['id']}.json": pulse_file(store, row, store.pulse(row["id"]))
            for row in catalog if store.pulse(row["id"]) is not None}


# ── theater dossiers ──────────────────────────────────────────────────────────────────────────
def dossier_files(built: dict) -> dict[str, dict]:
    """``theaters/<theater_id>.json`` per dossier plus ``theaters/index.json`` (``dossier.build_all`` output).
    No build timestamp of their own: ``built_at`` is the newest input's, so an unchanged dossier is stable."""
    files = {f"theaters/{tid}.json": d for tid, d in built["theaters"].items()}
    files["theaters/index.json"] = built["index"]
    return files


# ── changes feed ──────────────────────────────────────────────────────────────────────────────
def _pulse_events(store: Any, catalog: list[dict]) -> list[dict]:
    out = []
    for row in catalog:
        pts = store.state(row["id"]).history
        base = {"pulse_id": row["id"], "name": row["name"], "url": "/pulses", "data_url": pulse_data_url(row["id"])}
        for n, pt in enumerate(pts):
            if n == 0:
                out.append({"type": "pulse_created", "at": pt.at, **base, "position": pt.position, "band": pt.band})
                continue
            prev = pts[n - 1]
            out.append({"type": "pulse_moved", "at": pt.at, **base, "from": prev.position, "to": pt.position,
                        "from_band": prev.band, "to_band": pt.band, "band_changed": prev.band != pt.band})
    return out


def _doc_events(reports: list[dict], briefs: list[dict]) -> list[dict]:
    out = [{"type": "daily_published", "at": r.get("built_at") or r["date"], "domain": r["domain"],
            "date": r["date"], "headline": (r.get("summary") or {}).get("headline", ""),
            "url": daily_url(r["date"]), "data_url": daily_data_url(r["domain"], r["date"])} for r in reports]
    out += [{"type": "brief_published", "at": b.get("built_at") or b.get("as_of", ""), "slug": b["slug"],
             "title": b.get("title", ""), "theater": b.get("theater_name", ""),
             "url": brief_url(b["slug"]), "data_url": brief_data_url(b["slug"])} for b in briefs]
    return out


def _forecast_events(intel_dir: Path) -> list[dict]:
    out = []
    for f in forecasts.current(intel_dir):
        links = {"url": brief_url(f["brief_slug"]), "data_url": "/data/forecasts.json"}
        base = {"forecast_id": f["id"], "statement": f["statement"], "probability": f["probability"], **links}
        out.append({"type": "forecast_made", "at": f["made_at"], **base})
        if f["status"] != "open":
            out.append({"type": "forecast_resolved", "at": f["resolved_at"], **base, "outcome": f["status"]})
    return out


def changes_file(store: Any, intel_dir: Path, catalog: list[dict], reports: list[dict], briefs: list[dict],
                 now: datetime) -> dict:
    """A rolling feed of what changed in the last 30 days, newest first, rebuilt from the stores each time
    (so it can never disagree with them). ``as_of`` is the newest event, keeping the file stable between changes."""
    end = now.astimezone(UTC)
    cutoff = end - timedelta(days=CHANGES_WINDOW_DAYS)
    events = _pulse_events(store, catalog) + _doc_events(reports, briefs) + _forecast_events(intel_dir)
    events = [e for e in events if e["at"] and cutoff <= _ts(e["at"]) <= end]
    events.sort(key=lambda e: (_ts(e["at"]), e["type"], json.dumps(e, sort_keys=True)), reverse=True)
    return {"schema": "ohmega.changes/1", "window_days": CHANGES_WINDOW_DAYS,
            "as_of": events[0]["at"] if events else "", "events": events}
