"""
The intel desk on the site — Pulses, hot theaters and briefs, as one data snapshot per build.

The site (static Next.js) reads this contract; keep it stable.

Snapshot file ``content/intel/snapshots/<slug>.json``, slug = UTC "YYYY-MM-DD-HHMM", kept forever
(archive)::

    {"schema":"ohmega.intel/1","slug","built_at",
     "situations":[{"id","title","summary","domain",
         "pulses":[{"id","name","question","low_end","high_end","position":float|null,
                    "band":"calm|elevated|severe|critical|unassessed","velocity_7d":float|null,
                    "velocity_30d":float|null,"confidence":str,"last_assessed":str,
                    "evidence_through":str,"history":[{"at","position"}],"rationale":str}],
         "watches":[{"condition","why","direction","horizon","status"}]}],   // open watches only
     "theaters":[{"id","name","domain","why","heat","trend","recent","prior",   // recent/prior: raw counts
                  "recent_share","prior_share",   // 0-1: share of all headlines in that 3-day window's
                                                  // editions; trend compares these, not the counts
                  "first_seen","series":[{"day","count","editions"}],   // editions = radar editions built
                                                  // that day; 0 = coverage gap, not a quiet day
                  "brief":slug|null}],            // newest board, hottest first;
                                                  // brief = newest brief slug for that theater id
     "briefs":[{"slug","title","bottom_line","theater_id","theater_name","as_of","direction","pace"}],
                                                                   // every brief ever, newest first
     "forecasts":{"scorecard":{"resolved","void","open","brier":float|null,   // lower is better, .25 = coin flip
                               "calibration":[{"range":"70-79","count","hit_rate"}]},
                  "open":[{"statement","probability","horizon","theater_name","brief_slug"}],   // 20 soonest horizon
                  "resolved":[{"statement","probability","outcome":"yes|no|void","resolved_at","evidence"}]}}
                                                                   // 20 newest resolved; from intel_store/forecasts.jsonl
     "daily":[{"domain","date","headline"}]}                       // every daily report, newest first

Brief files: ``content/intel/briefs/<slug>.json`` = the persisted brief record
(``intel_store/briefs/<slug>.json``, schema ``ohmega.brief/1``).

Daily files: ``content/intel/daily/<domain>/<YYYY-MM-DD>.json`` = the persisted daily report
(``intel_store/daily/<domain>/<date>.json``), schema ``ohmega.daily/1``::

    {"schema","domain","date","built_at","researched":bool,
     "summary":{"headline","the_day":[3-6 one-sentence bullets, most important first]},
     "theaters":[{"theater_id","name",
         "temperature":{"heat","trend","recent_share","prior_share"},
         "escalation":{"direction":"rising|steady|easing|unclear","pace":"fast|gradual|flat"},
         "pulses":[{"id","name","position":float|null,"band","change_24h":float|null,"change_7d":float|null}],
         "bottom_line","since_yesterday":[{"what","kind":"escalated|eased|new|resolved|unchanged"}],
         "developments":[{"headline","detail","when","where","actors":[...],
             "statements":[{"who","role","said","quote":bool,"when","source"}],   // quote=true: exact, <=25 words
             "significance","verification":"researched|reported","sources":[urls]}],
         "context":[{"what","when","why_relevant","source"}],   // older items that explain today
         "outlook","watch_next":[...],"brief_slug":slug|null,"map":null}],      // map reserved
     "cross_theater":[{"theaters":[names],"link"}],
     "pulse_proposals":[{"theater","name","question","low_end","high_end","why"}]}

Pulse numbers and deltas are computed from the Pulse store, never by a model.

Rules: ``rationale`` is the latest APPLIED, non-blind influence's rationale for that pulse, made
reader-safe (claim ids stripped, ~400 chars at a word boundary). Situations that are not "active"
and pulses that are "dormant" are skipped. ``absolute_position`` is internal and never exported.
Situations list assessed ones first (most severe pulse first); pulses inside by position desc,
unassessed last.

Like the radar, the files are data, not markup — the site renders them.
"""

from __future__ import annotations

import json
import re
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from algent_backend.agent_system.agents.intel import forecasts
from algent_backend.agent_system.agents.intel.brief import safe_name

from . import site_git

INTEL_SUBDIR = ("content", "intel")
SCHEMA = "ohmega.intel/1"
_MAX_RATIONALE = 400
_CLAIM_ID = re.compile(r"\bclm_[0-9a-f]+\b")


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


def _rationale(store: Any, pulse_id: str) -> str:
    applied = [i for i in store.log(pulse_id) if i.decision == "applied" and i.mode != "blind"]
    return reader_safe(max(applied, key=lambda i: i.at).rationale) if applied else ""


def _pulse(store: Any, pulse: Any) -> dict:
    st, d = store.state(pulse.id), pulse.definition
    return {"id": pulse.id, "name": pulse.name, "question": d.question, "low_end": d.low_end,
            "high_end": d.high_end, "position": st.position, "band": st.band or "unassessed",
            "velocity_7d": st.velocity_7d, "velocity_30d": st.velocity_30d, "confidence": st.confidence,
            "last_assessed": st.last_assessed, "evidence_through": st.evidence_through,
            "history": [{"at": p.at, "position": p.position} for p in st.history],
            "rationale": _rationale(store, pulse.id)}


def _situations(store: Any) -> list[dict]:
    out = []
    for sit in store.situations():
        if sit.status != "active":
            continue
        pulses = [_pulse(store, p) for p in store.pulses(sit.id) if p.status != "dormant"]
        pulses.sort(key=lambda p: (p["position"] is None, -(p["position"] or 0)))
        watches = [{"condition": w.condition, "why": w.why, "direction": w.expected_direction,
                    "horizon": w.horizon, "status": w.status}
                   for w in store.watches(sit.id) if w.status == "open"]
        out.append({"id": sit.id, "title": sit.title, "summary": sit.summary, "domain": sit.domain,
                    "pulses": pulses, "watches": watches})
    out.sort(key=lambda s: (not any(p["position"] is not None for p in s["pulses"]),
                            -max((p["position"] or 0 for p in s["pulses"]), default=0)))
    return out


def _read_all(folder: Path) -> list[dict]:
    out = []
    for path in sorted(folder.glob("*.json")) if folder.is_dir() else []:
        try:
            out.append(json.loads(path.read_text(encoding="utf-8")))
        except (OSError, ValueError):
            continue
    return out


def _daily_reports(intel_dir: Path) -> list[dict]:
    """Every persisted daily report, newest first (then by domain)."""
    rows = [r for folder in sorted((intel_dir / "daily").glob("*")) if folder.is_dir() for r in _read_all(folder)]
    return sorted(rows, key=lambda r: (r.get("date", ""), r.get("domain", "")), reverse=True)


def _forecasts(intel_dir: Path, theater_names: dict[str, str]) -> dict:
    """The desk's track record: the scorecard, what is still open, and how the latest calls came out."""
    rows = forecasts.current(intel_dir)
    open_ = sorted((f for f in rows if f["status"] == "open"), key=lambda f: f["horizon"])[:20]
    done = sorted((f for f in rows if f["status"] != "open"), key=lambda f: f["resolved_at"], reverse=True)[:20]
    return {"scorecard": forecasts.scorecard(intel_dir),
            "open": [{"statement": f["statement"], "probability": f["probability"], "horizon": f["horizon"],
                      "theater_name": theater_names.get(f["brief_slug"], ""), "brief_slug": f["brief_slug"]}
                     for f in open_],
            "resolved": [{"statement": f["statement"], "probability": f["probability"], "outcome": f["status"],
                          "resolved_at": f["resolved_at"], "evidence": f["evidence"]} for f in done]}


def build_snapshot(store: Any, intel_dir: Path, *, now: datetime | None = None) -> dict:
    """Everything the site shows of the desk, as of now. Pure read: nothing is written."""
    now = now or datetime.now(UTC)
    briefs = sorted(_read_all(intel_dir / "briefs"), key=lambda b: (b.get("as_of", ""), b.get("built_at", "")),
                    reverse=True)
    newest: dict[str, str] = {}
    for b in briefs:                                   # newest first, so the first one seen wins
        newest.setdefault(b.get("theater_id", ""), b["slug"])
    boards = sorted((intel_dir / "boards").glob("*.json")) if (intel_dir / "boards").is_dir() else []
    board = json.loads(boards[-1].read_text(encoding="utf-8")) if boards else {}
    theaters = {t["id"]: t for t in board.get("theaters", [])}
    rows = []
    for h in board.get("heat", []):                    # already hottest first
        t = theaters.get(h["theater_id"], {})
        rows.append({"id": h["theater_id"], "name": h.get("name") or t.get("name", ""),
                     "domain": t.get("domain", ""), "why": t.get("why", ""), "heat": h.get("heat", 0),
                     "trend": h.get("trend", ""), "recent": h.get("recent", 0), "prior": h.get("prior", 0),
                     "recent_share": h.get("recent_share", 0.0), "prior_share": h.get("prior_share", 0.0),
                     "first_seen": h.get("first_seen", ""), "series": h.get("series", []),
                     "brief": newest.get(h["theater_id"])})
    return {"schema": SCHEMA, "slug": now.astimezone(UTC).strftime("%Y-%m-%d-%H%M"),
            "built_at": now.isoformat(), "situations": _situations(store), "theaters": rows,
            "briefs": [{"slug": b["slug"], "title": b.get("title", ""), "bottom_line": b.get("bottom_line", ""),
                        "theater_id": b.get("theater_id", ""), "theater_name": b.get("theater_name", ""),
                        "as_of": b.get("as_of", ""), "direction": (b.get("escalation") or {}).get("direction", ""),
                        "pace": (b.get("escalation") or {}).get("pace", "")} for b in briefs],
            "forecasts": _forecasts(intel_dir, {b["slug"]: b.get("theater_name", "") for b in briefs}),
            "daily": [{"domain": r.get("domain", ""), "date": r.get("date", ""),
                       "headline": (r.get("summary") or {}).get("headline", "")} for r in _daily_reports(intel_dir)]}


def _write_if_changed(path: Path, payload: dict) -> None:
    text = json.dumps(payload, ensure_ascii=False, indent=2) + "\n"
    if path.is_file() and path.read_text(encoding="utf-8") == text:
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8", newline="\n")


def write_intel(site_dir: Path, snapshot: dict, intel_dir: Path) -> Path:
    """Write the snapshot and mirror every persisted brief and daily report into a site checkout (only what changed)."""
    root = site_dir.joinpath(*INTEL_SUBDIR)
    path = root / "snapshots" / f"{snapshot['slug']}.json"
    _write_if_changed(path, snapshot)
    for record in _read_all(intel_dir / "briefs"):
        _write_if_changed(root / "briefs" / f"{record['slug']}.json", record)
    for record in _daily_reports(intel_dir):
        _write_if_changed(root / "daily" / safe_name(record["domain"]) / f"{record['date']}.json", record)
    return path


def publish_intel() -> dict[str, Any]:
    """Put the desk snapshot live on the site. Never raises — the desk's work is already stored."""
    if not site_git.publish_enabled():
        return {"published": False, "note": "site publishing disabled"}
    try:
        from algent_backend.agent_system.agents.intel.heat import store_dir
        from algent_backend.agent_system.agents.pulse.repository import pulse_store

        root = site_git.repo_root()
        worktree, note = site_git.ensure_worktree(root)
        if worktree is None:
            return {"published": False, "note": note}
        snapshot = build_snapshot(pulse_store(), store_dir())
        path = write_intel(site_git.live_site_dir(root), snapshot, store_dir())
        ok, pushed = site_git.commit_and_push(worktree, f"intel({path.stem}): desk snapshot")
        return {"published": ok, "slug": path.stem, "note": pushed}
    except Exception as exc:  # noqa: BLE001
        return {"published": False, "note": f"{type(exc).__name__}: {str(exc)[:120]}"}
