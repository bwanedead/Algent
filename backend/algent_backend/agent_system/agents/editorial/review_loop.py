"""
The treatment-reviewer loop — (treatment, profile) -> TreatmentReview.

Tool-free: a single structured-output judgment. Fresh eyes over the planner's work, judged
against the source profile's evidence. The harness stamps identity and assigns finding ids;
the model brings the critique. LangGraph/LangChain imports live here; spec.py stays rail-free.
"""

from __future__ import annotations

from collections import Counter
from datetime import UTC, datetime
from typing import Any, TypedDict

from langchain_core.messages import HumanMessage, SystemMessage
from langchain_core.runnables import RunnableConfig
from langgraph.graph import END, START, StateGraph

from algent_backend.agent_system.agents.research.profile import SignalProfile
from algent_backend.agent_system.foundation.models import ModelSpec
from algent_backend.agent_system.runs import events as ev
from algent_backend.agent_system.runs.context import AgentRunContext

from .review_contracts import TreatmentReview
from .review_messages import build_treatment_review_message
from .review_prompts import SYSTEM_PROMPT
from .treatment import EditorialTreatment

ARTIFACT_NAME = "treatment_review.json"
REVIEW_COMPLETED = "treatment_review.completed"
REVIEW_NO_INPUT = "treatment_review.no_input"
GENERATOR = "treatment_reviewer@v1"


class ReviewState(TypedDict, total=False):
    treatment: dict[str, Any]         # the treatment to review (input)
    profile: dict[str, Any]           # its source profile (input — the evidence to judge against)
    treatment_review: dict[str, Any]  # the produced TreatmentReview


def build_treatment_reviewer_graph(context: AgentRunContext, *, model_spec: ModelSpec) -> Any:
    """Compile the treatment-reviewer graph (no tools — pure judgment)."""
    model = context.model_resolver.resolve(model_spec).client
    structured = model.with_structured_output(TreatmentReview)

    def review(state: ReviewState, config: RunnableConfig) -> dict[str, Any]:
        tdict, pdict = state.get("treatment"), state.get("profile")
        if not tdict or not pdict:
            return _finish(context, TreatmentReview(
                id="treatment_review_none", verdict="unsound",
                summary="treatment or source profile missing",
            ), event=REVIEW_NO_INPUT)

        treatment = EditorialTreatment.model_validate(tdict)
        profile = SignalProfile.model_validate(pdict)
        context.emit(ev.INPUT_PREVIEW, _input_preview(treatment))
        raw = structured.invoke(
            [SystemMessage(content=SYSTEM_PROMPT),
             HumanMessage(content=build_treatment_review_message(treatment, profile))],
            config=config,
        )
        report = raw if isinstance(raw, TreatmentReview) else TreatmentReview(
            id="", verdict="unsound", summary="reviewer returned no structured report",
        )
        return _finish(context, _finalize(report, treatment, model_spec.model), event=REVIEW_COMPLETED)

    graph = StateGraph(ReviewState)
    graph.add_node("review", review)
    graph.add_edge(START, "review")
    graph.add_edge("review", END)
    return graph.compile()


def _finalize(report: TreatmentReview, treatment: EditorialTreatment, model: str) -> TreatmentReview:
    findings = [f if f.id else f.model_copy(update={"id": f"tf_{i:02d}"})
                for i, f in enumerate(report.findings, 1)]
    return report.model_copy(update={
        "id": f"treatment_review_{treatment.id}",
        "treatment_id": treatment.id,
        "profile_id": treatment.profile_id,
        "findings": findings,
        "reviewer": GENERATOR,
        "model": model,
        "generated_at": datetime.now(UTC).isoformat(),
    })


def _finish(context: AgentRunContext, report: TreatmentReview, *, event: str) -> dict[str, Any]:
    link = None
    if context.artifacts is not None:
        context.artifacts.write_json(ARTIFACT_NAME, report.model_dump())
        link = "../artifacts/" + ARTIFACT_NAME
    context.emit(ev.OUTPUT_PREVIEW, _review_preview(report, link))
    context.emit(event, {
        "treatment_id": report.treatment_id,
        "verdict": report.verdict,
        "findings": len(report.findings),
        "blockers": sum(1 for f in report.findings if f.promotion_blocker),
    })
    return {"treatment_review": report.model_dump()}


def _review_preview(report: TreatmentReview, link: str | None) -> dict[str, Any]:
    by_sev = Counter(f.severity for f in report.findings)
    items = [f"[{f.severity}/{f.type}] {f.target}: {f.explanation[:70]}" for f in report.findings[:10]]
    if report.better_frame:
        items.insert(0, f"better frame? {report.better_frame[:80]}")
    return {
        "title": "treatment review (planning gauntlet)",
        "summary": f"verdict={report.verdict} | {len(report.findings)} findings {dict(by_sev)}",
        "items": items,
        "link": link,
    }


def _input_preview(t: EditorialTreatment) -> dict[str, Any]:
    return {
        "title": "input: treatment under review",
        "summary": f"{t.id} (rev {t.revision}) — frame: {t.chosen_frame.frame[:80]}",
        "top": [f"{len(t.concepts)} concepts, {len(t.perspectives)} perspectives"],
        "link": None,
    }
