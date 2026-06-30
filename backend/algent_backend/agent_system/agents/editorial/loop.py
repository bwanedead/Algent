"""
The editorial-planner loop — profile -> EditorialTreatment (the planning stage).

Tool-free: a single structured-output judgment over the profile. The model authors the
frame + the concept-molecule with LOCAL concept/perspective ids; the harness then owns
integrity — it assigns any missing ids and **validates every reference**: concept
dependencies must point at real concepts, and all grounding (concept `grounds_in`,
perspective `grounds_in`, `must_use_items`) must point at real profile item ids. Dangling
references are dropped, exactly as the profile assembly drops fabricated links — the model
reasons, the harness guarantees the graph is sound.

LangGraph/LangChain imports live here; spec.py stays rail-free.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any, TypedDict

from langchain_core.messages import HumanMessage, SystemMessage
from langchain_core.runnables import RunnableConfig
from langgraph.graph import END, START, StateGraph

from algent_backend.agent_system.agents.research.profile import SignalProfile
from algent_backend.agent_system.foundation.models import ModelSpec
from algent_backend.agent_system.runs import events as ev
from algent_backend.agent_system.runs.context import AgentRunContext

from .briefing import render_treatment
from .messages import build_treatment_message
from .prompts import SYSTEM_PROMPT
from .treatment import EditorialTreatment

ARTIFACT_JSON = "treatment.json"
ARTIFACT_MD = "treatment.md"
PLAN_COMPLETED = "treatment.completed"
PLAN_NO_INPUT = "treatment.no_input"
GENERATOR = "editorial_planner@v1"


class PlanState(TypedDict, total=False):
    profile: dict[str, Any]    # the profile to plan (the input)
    treatment: dict[str, Any]  # the produced EditorialTreatment


def build_planning_graph(context: AgentRunContext, *, model_spec: ModelSpec) -> Any:
    """Compile the planning graph for the given model (no tools — pure judgment)."""
    model = context.model_resolver.resolve(model_spec).client
    structured = model.with_structured_output(EditorialTreatment)

    def plan(state: PlanState, config: RunnableConfig) -> dict[str, Any]:
        pdict = state.get("profile")
        if not pdict:
            return _finish(context, EditorialTreatment(
                id="treatment_none", title="(no profile supplied)",
            ), event=PLAN_NO_INPUT)

        profile = SignalProfile.model_validate(pdict)
        context.emit(ev.INPUT_PREVIEW, _profile_preview(profile))
        raw = structured.invoke(
            [SystemMessage(content=SYSTEM_PROMPT),
             HumanMessage(content=build_treatment_message(profile))],
            config=config,
        )
        treatment = raw if isinstance(raw, EditorialTreatment) else EditorialTreatment(
            id="", title=profile.title,
        )
        return _finish(context, _finalize(treatment, profile, model_spec.model), event=PLAN_COMPLETED)

    graph = StateGraph(PlanState)
    graph.add_node("plan", plan)
    graph.add_edge(START, "plan")
    graph.add_edge("plan", END)
    return graph.compile()


def _finalize(t: EditorialTreatment, profile: SignalProfile, model: str) -> EditorialTreatment:
    """Stamp identity + validate every reference against the profile (drop dangling)."""
    valid_item_ids = {x.id for x in (
        *profile.claim_ledger, *profile.threads, *profile.source_ledger, *profile.entities,
    )}

    # Concept ids: keep the model's local ids; assign only for blanks.
    concepts = [c if c.id else c.model_copy(update={"id": f"k{i:02d}"})
                for i, c in enumerate(t.concepts, 1)]
    concept_ids = {c.id for c in concepts}
    concepts = [c.model_copy(update={
        "depends_on": [d for d in dict.fromkeys(c.depends_on) if d in concept_ids and d != c.id],
        "grounds_in": [g for g in dict.fromkeys(c.grounds_in) if g in valid_item_ids],
    }) for c in concepts]

    perspectives = [
        (p if p.id else p.model_copy(update={"id": f"p{i:02d}"})).model_copy(update={
            "grounds_in": [g for g in dict.fromkeys(p.grounds_in) if g in valid_item_ids],
        })
        for i, p in enumerate(t.perspectives, 1)
    ]

    return t.model_copy(update={
        "id": f"treatment_{profile.id}",
        "profile_id": profile.id,
        "title": t.title or profile.title,
        "concepts": concepts,
        "reader_path": [c for c in dict.fromkeys(t.reader_path) if c in concept_ids],
        "perspectives": perspectives,
        "must_use_items": [m for m in dict.fromkeys(t.must_use_items) if m in valid_item_ids],
        "generator": GENERATOR,
        "model": model,
        "generated_at": datetime.now(UTC).isoformat(),
    })


def _finish(context: AgentRunContext, t: EditorialTreatment, *, event: str) -> dict[str, Any]:
    link = None
    if context.artifacts is not None:
        context.artifacts.write_json(ARTIFACT_JSON, t.model_dump())
        context.artifacts.write_text(ARTIFACT_MD, render_treatment(t))
        link = "../artifacts/" + ARTIFACT_MD
    context.emit(ev.OUTPUT_PREVIEW, _treatment_preview(t, link))
    context.emit(event, {
        "profile_id": t.profile_id,
        "frame": t.chosen_frame.frame,
        "concepts": len(t.concepts),
        "perspectives": len(t.perspectives),
        "deception_risks": len(t.deception_risks),
    })
    return {"treatment": t.model_dump()}


def _treatment_preview(t: EditorialTreatment, link: str | None) -> dict[str, Any]:
    return {
        "title": "editorial treatment (planning stage)",
        "summary": f"frame: {t.chosen_frame.frame or '(none)'}  |  {len(t.concepts)} concepts, "
                   f"{len(t.perspectives)} perspectives, {len(t.deception_risks)} deception risks",
        "items": [f"[{c.id}] {c.name}" for c in t.concepts[:10]]
                 + [f"⚠ risk: {r[:72]}" for r in t.deception_risks[:4]],
        "link": link,
    }


def _profile_preview(profile: SignalProfile) -> dict[str, Any]:
    return {
        "title": "input: profile to plan",
        "summary": f"{profile.id} — {profile.title}  [status: {profile.profile_status}, "
                   f"{len(profile.claim_ledger)} claims, {len(profile.threads)} threads]",
        "top": [f"status: {profile.profile_status}"],
        "link": None,
    }
