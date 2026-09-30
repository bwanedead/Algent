"""
Scheduled reassessment — the self-audit that keeps Pulses honest.

Per Pulse, weekly:
1. ANCHORED — "is the current reading still justified by live evidence?" It sees its prior, the
   reasoning behind it, and (when a reconciliation is pending) the blind read that disagreed.
   This is what fights ratcheting: calm is evidence too, and a situation that has cooled should
   come back down.
2. BLIND — the same evidence and ruler with NO prior: "where does the evidence put it?" Recorded,
   never applied. Measured against the fresh anchored position, a gap wider than one band flags the
   Pulse for reconciliation, which the NEXT reassessment must address. (Blind-first would let the
   anchored pass clear the flag in the same breath and the signal would never be seen.)

Evidence = every claim the Pulse's history cites, plus the claims of every profile that fed it —
research Ohmega has already graded; nothing is fetched. Run ids are per ISO week, so a second run
in the same week is refused by the ledger's idempotency rather than double-counted.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any, Literal

from pydantic import BaseModel, Field

from .contracts import Confidence, Influence, Source
from .framing import describe
from .prompts import BLIND_ROLE, REASSESS_PROMPT_VERSION, REASSESS_ROLE
from .seed import evidence_block


class Reading(BaseModel):
    decision: Literal["applied", "no_change"] = "applied"
    position: float | None = None
    claim_ids: list[str] = Field(default_factory=list)
    rationale: str = ""
    confidence: Confidence = Field(default_factory=Confidence)
    evidence_through: str = ""


class WatchVerdict(BaseModel):
    watch_id: str
    status: Literal["keep", "expired", "invalidated"] = "keep"
    reason: str = ""


class Reassessment(Reading):
    watches: list[WatchVerdict] = Field(default_factory=list)


def week_run_id(now: datetime | None = None) -> str:
    year, week, _ = (now or datetime.now(UTC)).isocalendar()
    return f"reassess_{year}w{week:02d}"


def evidence_for(store: Any, pulse_id: str, profiles: dict[str, dict]) -> list[dict]:
    """The research this Pulse's history rests on: profiles it cited or that fed it."""
    log = store.log(pulse_id)
    cited = {c for i in log for c in i.source.claim_ids}
    fed = {i.source.profile_id for i in log if i.source.profile_id}
    out = []
    for pid, p in profiles.items():
        claims = p.get("claim_ledger") or []
        if pid in fed or any(isinstance(c, dict) and c.get("id") in cited for c in claims):
            out.append(p)
    return out


def reassess_pulse(context: Any, config: Any, store: Any, pulse: Any, profiles: dict[str, dict], *,
                   model_spec: Any, run_id: str) -> dict:
    from langchain_core.messages import HumanMessage, SystemMessage

    from algent_backend.agent_system.prompting import UNIVERSAL_AGENT_BASE, compose_system_prompt

    docs = evidence_for(store, pulse.id, profiles)
    evidence, citable = evidence_block(docs)
    state = store.state(pulse.id)
    if not docs:
        return {"pulse": pulse.id, "skipped": "no evidence yet"}
    now = datetime.now(UTC).isoformat()
    report: dict = {"pulse": pulse.id, "before": state.position}
    resolve = lambda role, schema: context.model_resolver.resolve(model_spec).client.with_structured_output(schema)  # noqa: E731

    last = next((i for i in reversed(store.log(pulse.id)) if i.decision == "applied" and i.mode != "blind"), None)
    blind_last = next((i for i in reversed(store.log(pulse.id)) if i.mode == "blind"), None)
    watches = [w for w in store.watches(pulse.situation_id) if w.status == "open" and pulse.id in w.pulse_ids]
    prior = ("unassessed" if state.position is None
             else f"{state.position:g} ({state.band}) — {last.rationale if last else ''}")
    pending = (f"\nRECONCILIATION PENDING: a blind read from evidence alone put this at "
               f"{blind_last.proposed_position:g} — {blind_last.rationale}. Address the disagreement."
               if state.needs_reconciliation and blind_last and blind_last.proposed_position is not None else "")
    anchored = resolve(REASSESS_ROLE, Reassessment).invoke([
        SystemMessage(content=compose_system_prompt(UNIVERSAL_AGENT_BASE, REASSESS_ROLE)),
        HumanMessage(content=f"{describe(pulse, store.log(pulse.id))}\n\nCURRENT READING: {prior}{pending}\n\n"
                             f"OPEN WATCHES:\n" + "\n".join(f"  {w.id}: {w.condition} (horizon {w.horizon or 'none'})" for w in watches)
                             + f"\n\nEVIDENCE:{evidence}\n\nTASK: is the reading still justified? Place it.")],
        config=config)
    if isinstance(anchored, Reassessment):
        report["anchored"] = _log(store, pulse, anchored, citable, mode="reassess", now=now, run_id=run_id)
        for v in anchored.watches:
            if v.status != "keep" and any(w.id == v.watch_id for w in watches):
                store.resolve_watch(v.watch_id, v.status, by=Source(run_id=run_id, stage="pulse_reassess"))
                report.setdefault("watches", []).append({v.watch_id: v.status})

    blind = resolve(BLIND_ROLE, Reading).invoke([
        SystemMessage(content=compose_system_prompt(UNIVERSAL_AGENT_BASE, BLIND_ROLE)),
        HumanMessage(content=f"{describe(pulse, blind=True)}\n\nEVIDENCE:{evidence}\n\nTASK: place it from the evidence alone.")],
        config=config)
    if isinstance(blind, Reading):
        report["blind"] = _log(store, pulse, blind, citable, mode="blind", now=now, run_id=run_id)
    after = store.state(pulse.id)
    report.update({"after": after.position, "anchoring_gap": after.anchoring_gap,
                   "needs_reconciliation": after.needs_reconciliation})
    return report


def _log(store: Any, pulse: Any, r: Reading, citable: set[str], *, mode: str, now: str, run_id: str) -> Any:
    good = [c for c in r.claim_ids if c in citable]
    position = r.position if (r.decision == "applied" and r.position is not None
                              and 0 <= r.position <= 100 and good) else None
    decision = "applied" if position is not None else "no_change"
    try:
        store.append(Influence(
            pulse_id=pulse.id, at=now, evidence_through=r.evidence_through, mode=mode,
            definition_version=pulse.definition.version, proposed_position=position,
            decision=decision, rationale=r.rationale or "—", confidence=r.confidence,
            prompt_version=REASSESS_PROMPT_VERSION,
            source=Source(run_id=run_id, stage=f"pulse_{mode}", claim_ids=good)))
    except Exception as exc:  # noqa: BLE001 — the same week twice is the idempotency working
        return {"refused": f"{type(exc).__name__}"}
    return {"decision": decision, "position": position}


def reassess_all(context: Any, config: Any, store: Any, *, model_spec: Any, only: str = "") -> list[dict]:
    from algent_backend.agent_system.agents.research.store import JsonProfileStore

    ps = JsonProfileStore()
    profiles = {i: p.model_dump() for i in ps.list_ids() if (p := ps.get(i)) is not None}
    run_id = week_run_id()
    out = []
    for pulse in store.pulses():
        if pulse.status == "dormant" or (only and pulse.id != only):
            continue
        try:
            out.append(reassess_pulse(context, config, store, pulse, profiles, model_spec=model_spec, run_id=run_id))
        except Exception as exc:  # noqa: BLE001 — one Pulse failing must not stop the week's audit
            out.append({"pulse": pulse.id, "error": f"{type(exc).__name__}: {str(exc)[:120]}"})
    return out
