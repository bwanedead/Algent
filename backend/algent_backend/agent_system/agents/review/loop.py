"""
The profile-reviewer loop — the gauntlet's first stage (profile -> ReviewReport).

Tool-free: a single structured-output judgment over the profile (it reviews what's there;
the enrichers do the searching later). LangGraph/LangChain imports live here; spec.py stays
rail-free. The run config is threaded to the model call so its token usage is metered.
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

from .contracts import ReviewReport
from .messages import build_review_message
from .prompts import SYSTEM_PROMPT

ARTIFACT_NAME = "review_report.json"
REVIEW_COMPLETED = "review.completed"
REVIEW_NO_INPUT = "review.no_input"
GENERATOR = "profile_reviewer@v1"


class ReviewState(TypedDict, total=False):
    profile: dict[str, Any]  # the profile to review (the input)
    review: dict[str, Any]   # the produced ReviewReport


def build_reviewer_graph(context: AgentRunContext, *, model_spec: ModelSpec) -> Any:
    """Compile the reviewer graph for the given model (no tools — pure judgment)."""
    model = context.model_resolver.resolve(model_spec).client
    structured = model.with_structured_output(ReviewReport)

    def review(state: ReviewState, config: RunnableConfig) -> dict[str, Any]:
        pdict = state.get("profile")
        if not pdict:
            return _finish(context, ReviewReport(
                id="review_none", verdict="unsound", summary="no profile supplied to review",
            ), event=REVIEW_NO_INPUT)

        profile = SignalProfile.model_validate(pdict)
        context.emit(ev.INPUT_PREVIEW, _profile_preview(profile))
        raw = structured.invoke(
            [SystemMessage(content=SYSTEM_PROMPT), HumanMessage(content=build_review_message(profile))],
            config=config,
        )
        report = raw if isinstance(raw, ReviewReport) else ReviewReport(
            id="", verdict="unsound", summary="reviewer returned no structured report",
        )
        return _finish(context, _finalize(report, profile, model_spec.model), event=REVIEW_COMPLETED)

    graph = StateGraph(ReviewState)
    graph.add_node("review", review)
    graph.add_edge(START, "review")
    graph.add_edge("review", END)
    return graph.compile()


def _finalize(report: ReviewReport, profile: SignalProfile, model: str) -> ReviewReport:
    findings = [f if f.id else f.model_copy(update={"id": f"find_{i:02d}"})
                for i, f in enumerate(report.findings, 1)]
    return report.model_copy(update={
        "id": f"review_{profile.id}",
        "profile_id": profile.id,
        "findings": findings,
        "reviewer": GENERATOR,
        "model": model,
        "generated_at": datetime.now(UTC).isoformat(),
    })


def _finish(context: AgentRunContext, report: ReviewReport, *, event: str) -> dict[str, Any]:
    link = None
    if context.artifacts is not None:
        context.artifacts.write_json(ARTIFACT_NAME, report.model_dump())
        link = "../artifacts/" + ARTIFACT_NAME
    context.emit(ev.OUTPUT_PREVIEW, _review_preview(report, link))
    context.emit(event, {
        "profile_id": report.profile_id,
        "verdict": report.verdict,
        "findings": len(report.findings),
        "blockers": sum(1 for f in report.findings if f.maturity_blocker),
    })
    return {"review": report.model_dump()}


def _review_preview(report: ReviewReport, link: str | None) -> dict[str, Any]:
    by_sev = Counter(f.severity for f in report.findings)
    return {
        "title": "profile review (gauntlet stage 1)",
        "summary": f"verdict={report.verdict} | {len(report.findings)} findings {dict(by_sev)} | "
                   f"lanes={report.recommended_lanes}",
        "items": [
            f"[{f.severity}/{f.type}] {f.target}: {f.explanation[:74]}  -> {f.lane or '?'}"
            for f in report.findings[:12]
        ],
        "link": link,
    }


def _profile_preview(profile: SignalProfile) -> dict[str, Any]:
    return {
        "title": "input: profile under review",
        "summary": f"{profile.id} — {profile.title}  [status: {profile.profile_status}, "
                   f"{len(profile.claim_ledger)} claims, {len(profile.threads)} threads]",
        "top": [f"status: {profile.profile_status}"],
        "link": None,
    }
