"""
The planning gauntlet (v1) — one bounded plan/review/revise round over a profile.

    plan -> review -> [if not promoted: revise -> re-review] -> PlanningGauntletReport

It chains the pieces that already work as sub-graphs under one run/context, so every stage's
events land in this run's timeline and a final verdict closes the loop. The treatment is the
pre-prose product; this is where it earns promotion. v1 is bounded: one revision pass, no
prose drafting. A still-`needs_revision` final verdict is a valid success — the lifecycle is
the point. The planner persists each treatment to the durable store (the revision keeps the
same id and bumps the revision), so the store ends holding the matured treatment.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any, TypedDict

from langchain_core.runnables import RunnableConfig
from langgraph.graph import END, START, StateGraph

from algent_backend.agent_system.runs import events as ev
from algent_backend.agent_system.runs.context import AgentRunContext

from .briefing import render_treatment
from .gauntlet_contracts import PlanningGauntletReport
from .review_spec import build_graph as build_treatment_reviewer
from .spec import build_graph as build_planner
from .treatment import EditorialTreatment

GAUNTLET_COMPLETED = "planning_gauntlet.completed"
GAUNTLET_NO_INPUT = "planning_gauntlet.no_input"


class GauntletState(TypedDict, total=False):
    profile: dict[str, Any]    # the profile to plan + put through the gauntlet (input)
    treatment: dict[str, Any]  # the final (possibly revised) treatment
    gauntlet: dict[str, Any]   # the PlanningGauntletReport


def build_planning_gauntlet_graph(context: AgentRunContext) -> Any:
    """Compile the planning-gauntlet orchestrator graph."""

    def run_gauntlet(state: GauntletState, config: RunnableConfig) -> dict[str, Any]:
        profile = state.get("profile")
        if not profile:
            context.emit(GAUNTLET_NO_INPUT, {"message": "no profile supplied to the planning gauntlet"})
            return {"gauntlet": PlanningGauntletReport(final_verdict="unsound").model_dump()}

        # 1. plan (essential under slim — required to publish)
        treatment = build_planner(context).invoke({"profile": profile}, config)["treatment"]
        _write(context, "treatment_initial.json", treatment)

        from algent_backend.agent_system.agents.newsroom import budget_policy
        from algent_backend.agent_system.foundation.models.budget_gate import (
            BudgetRefusedError,
        )

        # 2. review — optional once soft-capped; keep the draftable treatment.
        # Soft-ship the treatment, but never invent a "promoted" verdict for a skipped review.
        skipped_review = {"verdict": "not_reviewed", "findings": [], "better_frame": ""}
        if budget_policy.allow_optional("treatment_review"):
            try:
                review = build_treatment_reviewer(context).invoke(
                    {"treatment": treatment, "profile": profile}, config,
                )["treatment_review"]
            except BudgetRefusedError:
                from algent_backend.agent_system.foundation import cost

                cost.record_skip("treatment_review", cost.mode())
                review = skipped_review
        else:
            review = skipped_review
        _write(context, "review_initial.json", review)
        initial_verdict = review.get("verdict", "")
        initial_findings = len(review.get("findings", []))

        # 3. revise + re-review if not yet promoted (one bounded pass).
        # not_reviewed means the budget rail skipped judgment — do not revise against an empty critique.
        revised = False
        addressed: list[str] = []
        if initial_verdict not in ("promoted", "not_reviewed") and budget_policy.allow_optional(
            "treatment_revise",
        ):
            try:
                treatment = build_planner(context).invoke(
                    {
                        "profile": profile,
                        "prior_treatment": treatment,
                        "treatment_review": review,
                    },
                    config,
                )["treatment"]
                _write(context, "treatment_final.json", treatment)
                if budget_policy.allow_optional("treatment_review"):
                    review = build_treatment_reviewer(context).invoke(
                        {"treatment": treatment, "profile": profile}, config,
                    )["treatment_review"]
                    _write(context, "review_final.json", review)
                revised = True
                addressed = [
                    f.get("id", "")
                    for f in review.get("findings", [])
                    if not f.get("promotion_blocker")
                ]
            except BudgetRefusedError:
                from algent_backend.agent_system.foundation import cost

                cost.record_skip("treatment_revise", cost.mode())
                _write(context, "treatment_final.json", treatment)
        final_verdict = review.get("verdict", "")
        report = PlanningGauntletReport(
            profile_id=str(profile.get("id", "")),
            treatment_id=str(treatment.get("id", "")),
            starting_revision=1,
            ending_revision=int(treatment.get("revision", 1) or 1),
            revised=revised,
            promoted=final_verdict == "promoted",
            initial_verdict=initial_verdict, final_verdict=final_verdict,
            initial_findings=initial_findings,
            remaining_findings=len(review.get("findings", [])),
            remaining_blockers=sum(1 for f in review.get("findings", []) if f.get("promotion_blocker")),
            better_frame_offered=review.get("better_frame", ""),
            findings_addressed=addressed,
            generated_at=datetime.now(UTC).isoformat(),
        )
        if context.artifacts is not None:
            context.artifacts.write_json("treatment.json", treatment)
            context.artifacts.write_text("treatment.md", render_treatment(EditorialTreatment.model_validate(treatment)))
            context.artifacts.write_json("planning_gauntlet_report.json", report.model_dump())
        context.emit(ev.OUTPUT_PREVIEW, _preview(report))
        context.emit(GAUNTLET_COMPLETED, report.model_dump())
        return {"treatment": treatment, "gauntlet": report.model_dump()}

    graph = StateGraph(GauntletState)
    graph.add_node("gauntlet", run_gauntlet)
    graph.add_edge(START, "gauntlet")
    graph.add_edge("gauntlet", END)
    return graph.compile()


def _write(context: AgentRunContext, name: str, payload: Any) -> None:
    if context.artifacts is not None:
        context.artifacts.write_json(name, payload)


def _preview(report: PlanningGauntletReport) -> dict[str, Any]:
    return {
        "title": "planning gauntlet (1 round)",
        "summary": (
            f"{report.initial_verdict} (rev {report.starting_revision}) -> "
            f"{report.final_verdict} (rev {report.ending_revision}) | "
            f"{'revised' if report.revised else 'no revision'} | "
            f"remaining {report.remaining_findings} findings ({report.remaining_blockers} blockers)"
            + (f" | better frame offered: {report.better_frame_offered[:60]}" if report.better_frame_offered else "")
        ),
        "items": [f"promoted: {report.promoted}", f"treatment: {report.treatment_id}"],
        "link": "../artifacts/treatment.md",
    }
