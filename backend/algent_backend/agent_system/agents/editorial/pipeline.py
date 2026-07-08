"""
The editorial pipeline (v1) — profile -> planning gauntlet -> drafting gauntlet -> article.

One run turns a research profile into a finished article, chaining the two gauntlets that
already work as sub-graphs under one run/context (so every stage's events land in this run's
timeline). It does NOT hard-gate on the planning verdict — the drafter writes from the best
treatment available, and the article is always produced; the report carries the quality signals
(treatment verdict, draft outcome, walls caveated) that the eventual human approval surface
reads. The upstream research + profile gauntlet are separate, proven stages; prepend them to go
from a raw vector.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any, TypedDict

from langchain_core.runnables import RunnableConfig
from langgraph.graph import END, START, StateGraph

from algent_backend.agent_system.agents.research.profile import SignalProfile
from algent_backend.agent_system.runs import events as ev
from algent_backend.agent_system.runs.context import AgentRunContext

from .draft import ArticleDraft
from .draft_gauntlet import build_drafting_gauntlet_graph
from .draft_store import render_draft
from .gauntlet import build_planning_gauntlet_graph
from .pipeline_contracts import EditorialPipelineReport
from .publish import render_published_article

PIPELINE_COMPLETED = "editorial_pipeline.completed"
PIPELINE_NO_INPUT = "editorial_pipeline.no_input"


class PipelineState(TypedDict, total=False):
    profile: dict[str, Any]    # the research profile to turn into an article (input)
    treatment: dict[str, Any]  # the planned treatment
    draft: dict[str, Any]      # the finished article
    pipeline: dict[str, Any]   # the EditorialPipelineReport


def build_editorial_pipeline_graph(context: AgentRunContext) -> Any:
    """Compile the end-to-end editorial pipeline (profile -> article)."""

    def run(state: PipelineState, config: RunnableConfig) -> dict[str, Any]:
        profile = state.get("profile")
        if not profile:
            context.emit(PIPELINE_NO_INPUT, {"message": "no profile supplied to the editorial pipeline"})
            return {"pipeline": EditorialPipelineReport().model_dump()}

        # 1. plan (the planning gauntlet: plan -> review -> revise -> re-review).
        plan_out = build_planning_gauntlet_graph(context).invoke({"profile": profile}, config)
        treatment = plan_out.get("treatment") or {}
        plan_report = plan_out.get("gauntlet") or {}

        # 2. draft (the drafting gauntlet: draft -> audit -> revise until grounded/caveated).
        draft_out = build_drafting_gauntlet_graph(context).invoke(
            {"treatment": treatment, "profile": profile}, config)
        draft = draft_out.get("draft") or {}
        enriched_profile = draft_out.get("profile") or profile   # final grounding state for the appendix
        draft_report = draft_out.get("gauntlet") or {}

        outcome = str(draft_report.get("outcome", ""))
        # A clean grounded piece is publishable; a caveated one is publishable ONLY once a human
        # (or v3b) confirms the prose actually carries the hedge — say so honestly.
        status = {
            "grounded": "publishable",
            "grounded_with_caveats": "publishable_pending_caveat_check",
        }.get(outcome, "blocked")
        # A drifted/unverified figure is also an unverified promise — fold it into the pending
        # status so `status` stays the single honest signal for the approval surface.
        if status == "publishable" and draft_report.get("unverified_figures"):
            status = "publishable_pending_caveat_check"

        report = EditorialPipelineReport(
            profile_id=str(profile.get("id", "")),
            treatment_id=str(treatment.get("id", "")),
            treatment_verdict=str(plan_report.get("final_verdict", "")),
            draft_id=str(draft.get("id", "")),
            draft_outcome=outcome,
            publishable=bool(draft_report.get("promoted", False)),
            status=status,
            article_title=str(draft.get("title", "")),
            word_count=int(draft.get("word_count", 0) or 0),
            barriers=draft_report.get("barriers", []),
            unverified_figures=draft_report.get("unverified_figures", []),
            generated_at=datetime.now(UTC).isoformat(),
        )
        if context.artifacts is not None and draft:
            draft_obj = ArticleDraft.model_validate(draft)
            # The reader-facing piece + transparency appendix, and the annotated draft for audit.
            context.artifacts.write_text(
                "article_published.md",
                render_published_article(draft_obj, SignalProfile.model_validate(enriched_profile)))
            context.artifacts.write_text("article.md", render_draft(draft_obj))
            context.artifacts.write_json("editorial_pipeline_report.json", report.model_dump())
        context.emit(ev.OUTPUT_PREVIEW, _preview(report))
        context.emit(PIPELINE_COMPLETED, report.model_dump())
        return {"treatment": treatment, "draft": draft, "pipeline": report.model_dump()}

    graph = StateGraph(PipelineState)
    graph.add_node("pipeline", run)
    graph.add_edge(START, "pipeline")
    graph.add_edge("pipeline", END)
    return graph.compile()


def _preview(r: EditorialPipelineReport) -> dict[str, Any]:
    return {
        "title": f"article: {r.article_title[:70] or '(untitled)'}",
        "summary": (
            f"{r.word_count} words | status: {r.status} | draft: {r.draft_outcome} | "
            f"treatment: {r.treatment_verdict}"
            + (f" | walls caveated: {r.barriers}" if r.barriers else "")
        ),
        "items": [f"treatment: {r.treatment_id}", f"draft: {r.draft_id}"],
        "link": "../artifacts/article.md",
    }
