"""
The forecast ledger — the desk's key judgments, kept so they can be scored.

A brief that says "likely" and is never checked teaches nothing. Every judgment a brief makes is
appended to ``intel_store/forecasts.jsonl`` as an open forecast; a resolution is a SEPARATE appended
line, never an edit. The current status of a forecast is a projection (the latest resolution line
wins), the same shape as the Pulse influence log: history is never rewritten, so the track record
cannot be quietly improved after the fact. The scorecard (Brier score, calibration by probability
decile) is what tells readers — and the analyst, who is shown its own misses — how far to trust us.

Lines::

    open:     {id, brief_slug, theater_id, made_at, statement, probability, horizon, basis,
               resolves_yes_if, resolves_no_if, status:"open"}
    resolve:  {id, resolved_at, outcome:"yes"|"no"|"void", evidence, by}
"""

from __future__ import annotations

import hashlib
import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Literal

from pydantic import BaseModel, Field

from .contracts import Judgment
from .heat import store_dir

OUTCOMES = ("yes", "no", "void")


def forecast_id(brief_slug: str, statement: str) -> str:
    return "fc_" + hashlib.sha1(f"{brief_slug}\n{' '.join(statement.split())}".encode()).hexdigest()[:12]


def _ledger(root: Path | None) -> Path:
    return (root or store_dir()) / "forecasts.jsonl"


def _lines(root: Path | None) -> list[dict]:
    path = _ledger(root)
    out = []
    for raw in path.read_text(encoding="utf-8").splitlines() if path.is_file() else []:
        try:
            out.append(json.loads(raw))
        except ValueError:
            continue                                   # a torn line must not hide the rest of the ledger
    return out


def _append(root: Path | None, rows: list[dict]) -> None:
    path = _ledger(root)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8", newline="\n") as fh:
        for row in rows:
            fh.write(json.dumps(row, ensure_ascii=False) + "\n")


def record(brief_slug: str, theater_id: str, judgments: list[Judgment], *, made_at: str = "",
           root: Path | None = None) -> list[str]:
    """Append a brief's judgments as open forecasts. Idempotent: an id already in the ledger is skipped."""
    known = {r["id"] for r in _lines(root) if "statement" in r}
    rows = []
    for j in judgments:
        fid = forecast_id(brief_slug, j.statement)
        if fid in known:
            continue
        known.add(fid)
        rows.append({"id": fid, "brief_slug": brief_slug, "theater_id": theater_id,
                     "made_at": made_at or datetime.now(UTC).isoformat(), "statement": j.statement,
                     "probability": j.probability, "horizon": j.horizon, "basis": j.basis,
                     "resolves_yes_if": j.resolves_yes_if, "resolves_no_if": j.resolves_no_if,
                     "status": "open"})
    _append(root, rows)
    return [r["id"] for r in rows]


def resolve(fid: str, outcome: str, evidence: str, *, by: str = "desk", at: str = "",
            root: Path | None = None) -> bool:
    """Append a resolution for a known forecast. False (nothing written) for an unknown id or outcome."""
    if outcome not in OUTCOMES or not any(r["id"] == fid and "statement" in r for r in _lines(root)):
        return False
    _append(root, [{"id": fid, "resolved_at": at or datetime.now(UTC).isoformat(), "outcome": outcome,
                    "evidence": evidence.strip(), "by": by}])
    return True


def resolutions(root: Path | None = None) -> dict[str, dict]:
    """The latest resolution line per forecast id."""
    return {r["id"]: r for r in _lines(root) if "outcome" in r}


def current(root: Path | None = None) -> list[dict]:
    """Every forecast with its projected status: ``open`` or the latest resolution's outcome."""
    res = resolutions(root)
    out = []
    for r in _lines(root):
        if "statement" not in r:
            continue
        done = res.get(r["id"])
        out.append({**r, "status": done["outcome"] if done else "open",
                    "resolved_at": done["resolved_at"] if done else "",
                    "evidence": done.get("evidence", "") if done else "",
                    "resolved_by": done.get("by", "") if done else ""})
    return out


def due(as_of: str, *, theater_id: str = "", root: Path | None = None) -> list[dict]:
    """Open forecasts worth resolving now: past their horizon, or — when a theater is being briefed —
    any open one for that theater (it can resolve early when the evidence is already decisive)."""
    return [f for f in current(root) if f["status"] == "open"
            and (f["horizon"] <= as_of or (theater_id and f["theater_id"] == theater_id))]


def scorecard(root: Path | None = None) -> dict:
    """Resolved count, Brier score (mean (p - outcome)^2 over yes/no; lower is better, 0.25 is a coin
    flip) and calibration by probability decile — when we say 70%, does it happen about 70% of the time."""
    rows = current(root)
    scored = [(f["probability"] / 100, 1 if f["status"] == "yes" else 0) for f in rows if f["status"] in ("yes", "no")]
    buckets: dict[int, list[int]] = {}
    for p, o in scored:
        buckets.setdefault(min(int(p * 10), 9), []).append(o)
    return {"resolved": len(scored), "void": sum(f["status"] == "void" for f in rows),
            "open": sum(f["status"] == "open" for f in rows),
            "brier": round(sum((p - o) ** 2 for p, o in scored) / len(scored), 4) if scored else None,
            "calibration": [{"range": f"{d * 10}-{d * 10 + 9}", "count": len(v), "hit_rate": round(sum(v) / len(v), 3)}
                            for d, v in sorted(buckets.items())]}


def track_record(theater_id: str, *, root: Path | None = None, limit: int = 8) -> str:
    """The desk's own prior calls on a theater, outcomes included — shown to the analyst so it learns
    from its misses rather than repeating a confident error."""
    rows = [f for f in current(root) if f["theater_id"] == theater_id][-limit:]
    return "\n".join(f"- [{f['status'].upper()}] {f['probability']}% by {f['horizon']}: {f['statement']}"
                     + (f" — {f['evidence'][:200]}" if f["evidence"] else "") for f in rows)


# ── the resolver ──────────────────────────────────────────────────────────────────────────────
RESOLVER_ROLE = """\
You are the scorekeeper of an intelligence desk. You are given forecasts the desk made earlier —
each a falsifiable claim with a probability, a horizon, and the conditions that would make it YES
or NO — and the newest evidence the desk has. Decide which forecasts the evidence actually settles.

- yes: the resolves_yes_if condition is met by the evidence. A forecast may resolve yes before its
  horizon when the evidence is decisive.
- no: the resolves_no_if condition is met. Before the horizon, only when that is already
  unavoidable. After the horizon, absence can settle it: if the horizon has passed, the event the
  forecast needed has not occurred, and the evidence covers the period well enough that you would
  expect to have seen it, that is a no — say so in the evidence field.
- void: the question was overtaken so that neither condition can any longer be judged (the premise
  disappeared, the terms were ill-defined). Not a way to avoid an awkward no.
- not_yet: the evidence does not settle it, the horizon has not passed, or the evidence is too thin
  to tell silence from missing coverage. Leave it open — an honest "not yet" costs nothing, a
  wrong resolution corrupts the track record every later reader relies on.

Judge only against the evidence supplied and the dates given, never against what you remember.
Quote or paraphrase the specific item that settles each one in `evidence`. Do not soften a miss:
the desk learns from being scored honestly.
"""


class Resolution(BaseModel):
    id: str
    outcome: Literal["yes", "no", "void", "not_yet"] = "not_yet"
    evidence: str = ""


class ResolutionPlan(BaseModel):
    resolutions: list[Resolution] = Field(default_factory=list)


def resolve_due(context: Any, config: Any, model_spec: Any, evidence_text: str, *, as_of: str,
                theater_id: str = "", root: Path | None = None) -> list[dict]:
    """Ask the model which due forecasts the evidence settles; append a line for each. Returns them.

    Only ids that were actually due are accepted and a verdict without evidence is dropped, so a
    confused model cannot write into the ledger on its own say-so.
    """
    from langchain_core.messages import HumanMessage, SystemMessage

    from algent_backend.agent_system.prompting import UNIVERSAL_AGENT_BASE, compose_system_prompt

    pending = {f["id"]: f for f in due(as_of, theater_id=theater_id, root=root)}
    if not pending or not evidence_text.strip():
        return []
    listing = "\n".join(
        f"[{f['id']}] {f['probability']}% — {f['statement']}\n  horizon: {f['horizon']}"
        f"{' (PASSED)' if f['horizon'] <= as_of else ''} · made {f['made_at'][:10]}\n"
        f"  YES if: {f['resolves_yes_if'] or '—'}\n  NO if: {f['resolves_no_if'] or '—'}" for f in pending.values())
    task = (f"TODAY: {as_of}\n\nFORECASTS:\n{listing}\n\nEVIDENCE:\n{evidence_text}\n\n"
            "TASK: resolve what the evidence settles; mark the rest not_yet.")
    model = context.model_resolver.resolve(model_spec).client.with_structured_output(ResolutionPlan)
    plan = model.invoke([SystemMessage(content=compose_system_prompt(UNIVERSAL_AGENT_BASE, RESOLVER_ROLE)),
                         HumanMessage(content=task)], config=config)
    settled = []
    for r in getattr(plan, "resolutions", []) or []:
        if r.id in pending and r.outcome in OUTCOMES and r.evidence.strip() \
                and resolve(r.id, r.outcome, r.evidence, by="desk", root=root):
            settled.append({"id": r.id, "outcome": r.outcome})
            pending.pop(r.id)                          # one verdict per forecast per pass
    return settled
