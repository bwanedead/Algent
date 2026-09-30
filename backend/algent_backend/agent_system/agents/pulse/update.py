"""
The article update — how every piece of research Ohmega finishes feeds its Pulses.

After an article run, its research profile is:
1. ATTACHED to the situations it genuinely belongs to (same judgment as seeding);
2. for each touched situation, every Pulse is RE-ESTIMATED: given its ruler, its current position
   and reasoning, and the new graded claims, where does it sit now? A position or "no_change" —
   both are logged, because knowing the machine considered an event and dismissed it is half the
   audit trail;
3. the answer is CHECKED like a seed: a move needs a valid cited claim from THIS research, or it is
   recorded as no_change with the reason; unknown Pulses and off-ruler positions are refused;
4. open watches the evidence fulfils are resolved, and the event is recorded once.

Never raises into the caller: a Pulse problem must never cost an article (``update_quietly``).
Consumes only graded research — it never fetches anything.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any, Literal

from pydantic import BaseModel, Field

from .catalog import SeedSituation
from .contracts import Confidence, Event, Influence, Source, event_id
from .prompts import UPDATE_PROMPT_VERSION, UPDATE_ROLE
from .seed import attach, evidence_block


class PulseUpdate(BaseModel):
    pulse_id: str
    decision: Literal["applied", "no_change"] = "no_change"
    position: float | None = None
    claim_ids: list[str] = Field(default_factory=list)
    rationale: str = ""
    confidence: Confidence = Field(default_factory=Confidence)
    evidence_through: str = ""


class WatchHit(BaseModel):
    watch_id: str
    claim_id: str = ""


class EventDraft(BaseModel):
    summary: str = ""
    occurred_on: str = ""
    place: str = ""


class UpdatePlan(BaseModel):
    event: EventDraft | None = None
    updates: list[PulseUpdate] = Field(default_factory=list)
    watches_triggered: list[WatchHit] = Field(default_factory=list)


def _situation_brief(store: Any, sit: Any) -> tuple[str, dict[str, Any]]:
    """The Pulses of one situation as the model sees them: ruler, current reading, open watches."""
    lines, pulses = [f"SITUATION: {sit.title}\n{sit.summary}"], {}
    for pulse in store.pulses(sit.id):
        if pulse.status == "dormant":
            continue
        st = store.state(pulse.id)
        last = next((i for i in reversed(store.log(pulse.id)) if i.decision == "applied"), None)
        pulses[pulse.id] = pulse
        d = pulse.definition
        lines.append(f"\n### {pulse.id} — {pulse.name} (ruler v{d.version})\n{d.question}")
        lines += [f"  {a.position:g}: {a.meaning}" for a in d.anchors]
        lines.append(f"  CURRENT: {'unassessed' if st.position is None else f'{st.position:g} ({st.band})'}"
                     + (f" — {last.rationale}" if last else ""))
    watches = [w for w in store.watches(sit.id) if w.status == "open"]
    if watches:
        lines.append("\nOPEN WATCHES:")
        lines += [f"  {w.id}: {w.condition}" for w in watches]
    return "\n".join(lines), pulses


def update_from_profile(context: Any, config: Any, store: Any, profile: dict, *,
                        run_id: str, article_slug: str = "", model_spec: Any,
                        attach_spec: Any) -> dict:
    """Feed one finished piece of research into the Pulses it touches. Returns a report."""
    from langchain_core.messages import HumanMessage, SystemMessage

    from algent_backend.agent_system.prompting import UNIVERSAL_AGENT_BASE, compose_system_prompt

    situations = [s for s in store.situations() if s.status == "active"]
    if not situations:
        return {"touched": [], "note": "no situations yet"}
    as_seed = tuple(SeedSituation(s.id, s.title, s.summary or s.title, s.domain) for s in situations)
    links = attach(context, config, [profile], situations=as_seed, model_spec=attach_spec)
    touched = [s for s in situations if profile.get("id") in links.get(s.id, [])]
    evidence, citable = evidence_block([profile])
    now = datetime.now(UTC).isoformat()
    report: dict = {"touched": [s.id for s in touched], "influences": [], "watches": [], "problems": []}
    prompt = compose_system_prompt(UNIVERSAL_AGENT_BASE, UPDATE_ROLE)
    model = context.model_resolver.resolve(model_spec).client.with_structured_output(UpdatePlan)

    for sit in touched:
        brief, pulses = _situation_brief(store, sit)
        if not pulses:
            continue
        plan = model.invoke([SystemMessage(content=prompt), HumanMessage(content=(
            f"{brief}\n\nNEW RESEARCH — graded claims:{evidence}\n\n"
            "TASK: for every Pulse above, where does it sit now (or no_change)? Then any watch "
            "fulfilled, and the event this research is about."))], config=config)
        if not isinstance(plan, UpdatePlan):
            report["problems"].append(f"{sit.id}: model returned no plan")
            continue
        evt = None
        if plan.event and plan.event.summary.strip():
            evt = store.record_event(Event(
                id=event_id(plan.event.summary, plan.event.occurred_on), summary=plan.event.summary,
                occurred_on=plan.event.occurred_on, place=plan.event.place, situation_ids=[sit.id],
                sources=[Source(run_id=run_id, article_slug=article_slug, profile_id=str(profile.get("id") or ""))]))
        for u in plan.updates:
            inf = _checked_influence(u, pulses, citable, report["problems"], now=now, run_id=run_id,
                                     article_slug=article_slug, profile_id=str(profile.get("id") or ""),
                                     event=evt.id if evt else "")
            if inf is None:
                continue
            try:
                store.append(inf)
                report["influences"].append({"pulse": inf.pulse_id, "decision": inf.decision,
                                             "position": inf.proposed_position})
            except Exception as exc:  # noqa: BLE001 — a duplicate on retry is the idempotency working
                report["problems"].append(f"{inf.pulse_id}: {type(exc).__name__}: {str(exc)[:80]}")
        open_ids = {w.id for w in store.watches(sit.id) if w.status == "open"}
        for hit in plan.watches_triggered:
            if hit.watch_id in open_ids and hit.claim_id in citable:
                store.resolve_watch(hit.watch_id, "triggered", by=Source(
                    run_id=run_id, article_slug=article_slug, claim_ids=[hit.claim_id],
                    event_id=evt.id if evt else ""))
                report["watches"].append(hit.watch_id)
    return report


def _checked_influence(u: PulseUpdate, pulses: dict, citable: set[str], problems: list[str], *,
                       now: str, run_id: str, article_slug: str, profile_id: str, event: str) -> Influence | None:
    pulse = pulses.get(u.pulse_id)
    if pulse is None:
        problems.append(f"unknown pulse {u.pulse_id} refused")
        return None
    good = [c for c in u.claim_ids if c in citable]
    decision, position, rationale = u.decision, u.position, u.rationale
    if decision == "applied" and (position is None or not 0 <= position <= 100 or not good):
        problems.append(f"{u.pulse_id}: move to {position} lacked valid evidence — logged as no_change")
        decision, position = "no_change", None
        rationale = f"[move refused: no valid evidence] {rationale}"
    if decision == "no_change":
        position = None
    return Influence(
        pulse_id=u.pulse_id, at=now, evidence_through=u.evidence_through, mode="article",
        definition_version=pulse.definition.version, proposed_position=position, decision=decision,
        rationale=rationale or "no rationale given", confidence=u.confidence,
        prompt_version=UPDATE_PROMPT_VERSION,
        source=Source(run_id=run_id, stage="pulse_update", profile_id=profile_id,
                      article_slug=article_slug, claim_ids=good, event_id=event))


def update_quietly(profile: dict, *, run_id: str, article_slug: str = "") -> dict:
    """The rail's entry point. Never raises: a Pulse problem must never cost an article."""
    try:
        from algent_backend.agent_system.foundation.models import ModelResolver, house_spec
        from algent_backend.agent_system.runs.context import AgentRunContext

        from .repository import pulse_store

        ctx = AgentRunContext(run_id=run_id, model_resolver=ModelResolver())
        return update_from_profile(
            ctx, None, pulse_store(), profile, run_id=run_id, article_slug=article_slug,
            model_spec=house_spec(reasoning_effort="medium", temperature=0.2, max_tokens=16384),
            attach_spec=house_spec(reasoning_effort="low", temperature=0.1))
    except Exception as exc:  # noqa: BLE001
        return {"touched": [], "error": f"{type(exc).__name__}: {str(exc)[:160]}"}
