"""
The Pulse registry — the one door for creating Pulses outside seeding, and the agent-facing catalog.

Pulses are stable objects that grow from the work, with no top-down curator. Anyone (the daily
report, a brief, an operator, later an external agent) may PROPOSE a Pulse; a proposal that recurs
becomes a real one; guards keep the catalog clean (one dimension, one Pulse).

The proposals ledger is owned by the Pulse store (append-only, ``propose``/``proposals``). Its lines:
- ``sighting``  — {kind, id, at, source{kind, run_id, theater_id, domain}, situation_hint, name,
                  question, low_end, high_end, why}. The id is a stable hash of the normalised name
                  and question, so the same idea proposed again is another sighting of one proposal;
- ``promoted``  — {kind, id, at, pulse_id, situation_id}: it became a Pulse;
- ``duplicate`` — {kind, id, at, duplicate_of, reason}: it measures a dimension a Pulse already measures.

Flow: ``propose`` validates and records a sighting; ``ready`` says which proposals have recurred;
``promote`` re-checks duplication, places the Pulse in a situation and creates it EXPERIMENTAL with
a v1 definition. Promotion never invents a position: the first reading comes later from the normal
updates, like any Pulse. Doctrine for the two model calls lives in ``prompts.py``.
"""

from __future__ import annotations

import hashlib
import json
import re
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from pydantic import BaseModel

from .contracts import Pulse, PulseDefinition, Situation
from .prompts import DEDUP_ROLE, PLACE_ROLE

SOURCE_KINDS = ("daily", "brief", "agent", "operator")
_FIELDS = ("name", "question", "low_end", "high_end", "why")
# A second question joined to the first ("How tense is X and how likely is Y?") is two dimensions.
_DOUBLE = re.compile(r"\band\s+(how|what|whether|why|when|will|is|are|do|does|can)\b", re.I)


class ProposalRejected(ValueError):
    """The proposal is malformed; the message lists every problem."""


class Verdict(BaseModel):
    duplicate_of: str | None = None
    reason: str = ""


class Placement(BaseModel):
    situation_id: str | None = None
    reason: str = ""


def _now() -> str:
    return datetime.now(UTC).isoformat()


def _norm(text: str) -> str:
    return " ".join(re.findall(r"[a-z0-9]+", (text or "").lower()))


def _slug(text: str) -> str:
    return _norm(text).replace(" ", "_")[:40].strip("_")


def proposal_id(name: str, question: str) -> str:
    return "prp_" + hashlib.sha1(f"{_norm(name)}|{_norm(question)}".encode()).hexdigest()[:12]


# ── the agent-facing catalog ──────────────────────────────────────────────────────────────────
def catalog(store: Any) -> list[dict]:
    """Every Pulse in an active situation as plain data: what it measures and where it stands now."""
    titles = {s.id: s.title for s in store.situations() if s.status == "active"}
    out = []
    for p in store.pulses():
        if p.situation_id not in titles:
            continue
        st, d = store.state(p.id), p.definition
        out.append({"id": p.id, "situation_id": p.situation_id, "situation": titles[p.situation_id],
                    "name": p.name, "question": d.question, "low_end": d.low_end, "high_end": d.high_end,
                    "status": p.status, "position": st.position, "band": st.band or "unassessed",
                    "confidence": st.confidence, "last_assessed": st.last_assessed,
                    "evidence_through": st.evidence_through, "velocity_7d": st.velocity_7d,
                    "history": [{"at": h.at, "position": h.position} for h in st.history]})
    return out


# ── proposing ─────────────────────────────────────────────────────────────────────────────────
def problems(proposal: dict) -> list[str]:
    """Mechanical guards only. The single-dimension check is a light heuristic (two questions joined
    by "and how/what/...", or more than one "?"); the semantic judgment belongs to ``is_duplicate``."""
    out = [f"missing {f}" for f in _FIELDS if not str(proposal.get(f) or "").strip()]
    src = proposal.get("source") or {}
    if src.get("kind") not in SOURCE_KINDS:
        out.append(f"source.kind must be one of {', '.join(SOURCE_KINDS)}")
    if not str(src.get("run_id") or "").strip():
        out.append("missing source.run_id (recurrence is counted across runs)")
    q = str(proposal.get("question") or "")
    if q.count("?") > 1 or _DOUBLE.search(q):
        out.append("question reads as two questions; one dimension, one Pulse")
    return out


def propose(store: Any, proposal: dict) -> dict:
    """Record one sighting of a proposal. Raises ``ProposalRejected`` when malformed. The same idea
    again appends another sighting (recurrence is the evidence); the identical sighting (same run and
    theater) is not written twice. Returns {id, recorded, sightings}."""
    found = problems(proposal)
    if found:
        raise ProposalRejected("; ".join(found))
    src = proposal["source"]
    pid = proposal_id(proposal["name"], proposal["question"])
    row = {"kind": "sighting", "id": pid, "at": proposal.get("at") or _now(),
           "source": {"kind": src["kind"], "run_id": str(src["run_id"]), "theater_id": src.get("theater_id", ""),
                      "domain": src.get("domain", "")},
           "situation_hint": str(proposal.get("situation_hint") or "").strip(),
           **{f: str(proposal[f]).strip() for f in _FIELDS}}
    mine = [r for r in store.proposals() if r.get("id") == pid and r.get("kind") == "sighting"]
    same = any(r["source"]["run_id"] == row["source"]["run_id"]
               and r["source"]["theater_id"] == row["source"]["theater_id"] for r in mine)
    if not same:
        store.propose(row)
    return {"id": pid, "recorded": not same, "sightings": len(mine) + (0 if same else 1)}


def summarize(lines: list[dict]) -> list[dict]:
    """The ledger folded into one row per proposal (first-seen order): the first sighting's text, how
    many sightings, the distinct runs and dates, its status, and whether it is ``ready``.

    READY means it was proposed independently at least twice: sightings from different run_ids on
    different dates. That is the minimal meaning of "recurring" (one run restating itself, or one day's
    reruns, is one voice), not a tuned threshold. Promoted or duplicate-rejected ones are never ready."""
    by: dict[str, dict] = {}
    for r in lines:
        pid = r.get("id", "")
        if r.get("kind") == "sighting":
            row = by.setdefault(pid, {**{k: r[k] for k in ("id", "name", "question", "low_end", "high_end",
                                                           "why", "situation_hint", "source")},
                                      "sightings": 0, "runs": set(), "dates": set(), "status": "open",
                                      "first_at": r["at"], "last_at": r["at"], "pulse_id": ""})
            row["sightings"] += 1
            row["runs"].add(r["source"]["run_id"])
            row["dates"].add(r["at"][:10])
            row["last_at"] = max(row["last_at"], r["at"])
        elif pid in by and r.get("kind") == "promoted":
            by[pid].update(status="promoted", pulse_id=r.get("pulse_id", ""))
        elif pid in by and r.get("kind") == "duplicate":
            by[pid].update(status="duplicate", duplicate_of=r.get("duplicate_of", ""))
    for row in by.values():
        row["runs"], row["dates"] = sorted(row["runs"]), sorted(row["dates"])
        row["ready"] = row["status"] == "open" and len(row["runs"]) >= 2 and len(row["dates"]) >= 2
    return list(by.values())


def ready(lines: list[dict]) -> list[dict]:
    return [r for r in summarize(lines) if r["ready"]]


# ── the model calls ───────────────────────────────────────────────────────────────────────────
def _ask(context: Any, config: Any, model_spec: Any, schema: Any, role: str, task: str) -> Any:
    from langchain_core.messages import HumanMessage, SystemMessage

    from algent_backend.agent_system.prompting import UNIVERSAL_AGENT_BASE, compose_system_prompt

    model = context.model_resolver.resolve(model_spec).client.with_structured_output(schema)
    return model.invoke([SystemMessage(content=compose_system_prompt(UNIVERSAL_AGENT_BASE, role)),
                         HumanMessage(content=task)], config=config)


def _describe(p: dict) -> str:
    return f"{p['name']}: {p['question']} (0 = {p['low_end']}; 100 = {p['high_end']})"


def is_duplicate(context: Any, config: Any, store: Any, proposal: dict, model_spec: Any) -> Verdict:
    """Does the proposal measure a dimension an existing Pulse already measures? An identical question
    is settled without a model; otherwise the model judges against the whole catalog."""
    cat = catalog(store)
    for c in cat:
        if _norm(c["question"]) == _norm(proposal["question"]):
            return Verdict(duplicate_of=c["id"], reason="the same question is already a Pulse")
    if not cat:
        return Verdict(reason="the catalog is empty")
    listing = "\n".join(f"- {c['id']} ({c['situation']}) {_describe(c)}" for c in cat)
    task = (f"EXISTING PULSES:\n{listing}\n\nPROPOSED PULSE:\n{_describe(proposal)}\nWhy proposed: "
            f"{proposal.get('why', '')}\n\nTASK: is the proposal a duplicate of an existing Pulse?")
    out = _ask(context, config, model_spec, Verdict, DEDUP_ROLE, task)
    if not isinstance(out, Verdict):
        return Verdict(reason="no verdict returned; treated as new")
    if out.duplicate_of and out.duplicate_of not in {c["id"] for c in cat}:
        return Verdict(reason=f"model named an unknown pulse {out.duplicate_of!r}; treated as new")
    return out


def _place(context: Any, config: Any, store: Any, proposal: dict, model_spec: Any) -> Situation | None:
    """The situation whose subject the dimension belongs to (model, against titles and summaries), or
    a new one opened from the hint. None when there is neither a fit nor a hint to name one."""
    domain = proposal["source"].get("domain") or "geopolitics"
    cands = [s for s in store.situations() if s.status == "active" and s.domain == domain]
    hint = proposal.get("situation_hint", "")
    if cands:
        listing = "\n".join(f"- {s.id}: {s.title} — {s.summary}" for s in cands)
        task = (f"HINT: {hint or 'none'}\nPROPOSED PULSE:\n{_describe(proposal)}\n\nSITUATIONS:\n{listing}\n\n"
                "TASK: which situation does this Pulse belong to?")
        out = _ask(context, config, model_spec, Placement, PLACE_ROLE, task)
        chosen = {s.id: s for s in cands}.get(getattr(out, "situation_id", None) or "")
        if chosen is not None:
            return chosen
    if not _slug(hint):
        return None
    sit_id = f"sit_{_slug(hint)}"
    if store.situation(sit_id) is None:
        store.save_situation(Situation(id=sit_id, domain=domain, title=hint, entities=[hint],
                                       summary=f"Opened from Pulse proposal {proposal['id']}."))
    return store.situation(sit_id)


# ── promoting ─────────────────────────────────────────────────────────────────────────────────
def promote(context: Any, config: Any, store: Any, proposal_id_: str, *, situation_id: str | None = None,
            model_spec: Any) -> dict:
    """Make a proposal a real Pulse. Returns {status, ...} with status one of promoted, duplicate,
    already_promoted, unknown_proposal, unknown_situation, no_situation. Never writes a position."""
    found = {r["id"]: r for r in summarize(store.proposals())}.get(proposal_id_)
    if found is None:
        return {"status": "unknown_proposal", "id": proposal_id_}
    if found["status"] == "promoted":
        return {"status": "already_promoted", "id": proposal_id_, "pulse_id": found["pulse_id"]}
    verdict = is_duplicate(context, config, store, found, model_spec)
    if verdict.duplicate_of:
        store.propose({"kind": "duplicate", "id": proposal_id_, "at": _now(),
                       "duplicate_of": verdict.duplicate_of, "reason": verdict.reason})
        return {"status": "duplicate", "id": proposal_id_, "duplicate_of": verdict.duplicate_of,
                "reason": verdict.reason}
    if situation_id:
        sit = store.situation(situation_id)
        if sit is None:
            return {"status": "unknown_situation", "id": proposal_id_, "situation_id": situation_id}
    else:
        sit = _place(context, config, store, found, model_spec)
        if sit is None:
            return {"status": "no_situation", "id": proposal_id_,
                    "note": "no fitting situation and no hint to open one; pass --situation"}
    pid = f"pls_{sit.id.removeprefix('sit_')}_{_slug(found['name'])}"
    if store.pulse(pid) is not None:
        pid += "_" + proposal_id_.removeprefix("prp_")[:6]
    note = f"promoted from proposal {proposal_id_}: {found['why']}"
    store.create_pulse(Pulse(id=pid, situation_id=sit.id, name=found["name"], status="experimental",
                             definitions=[PulseDefinition(question=found["question"], low_end=found["low_end"],
                                                          high_end=found["high_end"], note=note)]))
    store.propose({"kind": "promoted", "id": proposal_id_, "at": _now(), "pulse_id": pid,
                   "situation_id": sit.id})
    return {"status": "promoted", "id": proposal_id_, "pulse_id": pid, "situation_id": sit.id}


def promote_ready(context: Any, config: Any, store: Any, *, model_spec: Any) -> dict:
    """Promote every ready proposal (dedup included). One failure never stops the rest; the report says
    what happened to each. Never raises."""
    report: dict[str, Any] = {"promoted": [], "duplicates": [], "skipped": [], "errors": []}
    try:
        todo = ready(store.proposals())
    except Exception as exc:  # noqa: BLE001
        return {**report, "errors": [f"{type(exc).__name__}: {str(exc)[:120]}"]}
    for p in todo:
        try:
            out = promote(context, config, store, p["id"], model_spec=model_spec)
        except Exception as exc:  # noqa: BLE001
            report["errors"].append(f"{p['id']}: {type(exc).__name__}: {str(exc)[:120]}")
            continue
        bucket = {"promoted": "promoted", "duplicate": "duplicates"}.get(out["status"], "skipped")
        report[bucket].append({"name": p["name"], **out})
    return report


# ── the old intel_store ledger ────────────────────────────────────────────────────────────────
def migrate_legacy_proposals(path: Any, store: Any) -> dict:
    """One-shot, idempotent: replay ``intel_store/pulse_proposals.jsonl`` ({date, theater, theater_id,
    domain, name, question, low_end, high_end, why}) into the store as daily-kind sightings. The run id
    is derived from the date and domain, so a second pass writes nothing. Leaves the old file alone."""
    path = Path(path)
    done = bad = 0
    for line in path.read_text(encoding="utf-8").splitlines() if path.is_file() else []:
        try:
            r = json.loads(line)
            out = propose(store, {
                "at": f"{r['date']}T12:00:00+00:00", "situation_hint": r.get("theater", ""),
                "source": {"kind": "daily", "run_id": f"daily-{r.get('domain', '')}-{r['date']}",
                           "theater_id": r.get("theater_id", ""), "domain": r.get("domain", "")},
                **{f: r.get(f, "") for f in _FIELDS}})
            done += out["recorded"]
        except (ValueError, KeyError):
            bad += 1
    return {"migrated": done, "skipped_invalid": bad}
