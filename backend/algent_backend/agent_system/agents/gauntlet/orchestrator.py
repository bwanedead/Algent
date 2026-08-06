"""
The gauntlet orchestrator (v1) — one bounded review/enrichment round over a profile.

Chains the pieces that already work, sequentially (so enricher additions merge in a
deterministic order — each lane enriches the prior lane's result, so no rev-2 can
overwrite another):

    review -> [primary_source enrich -> merge] -> [counter_perspective enrich -> merge]
           -> re-render -> re-review -> GauntletReport

It invokes the existing reviewer/enricher graphs as sub-graphs (identical behavior to
running them standalone), under one run/context — so every stage's events land in this
run's timeline and a re-review verdict closes the loop. v1 is bounded: one round, these
two lanes, no article generation, no analytics worker. A still-`needs_enrichment` verdict
is a valid success — the point is to prove the lifecycle, not to force maturity.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any, TypedDict

from langchain_core.runnables import RunnableConfig
from langgraph.graph import END, START, StateGraph

from algent_backend.agent_system.agents.enrich import counter_perspective, primary_source
from algent_backend.agent_system.agents.research.briefing import render_briefing
from algent_backend.agent_system.agents.research.profile import SignalProfile
from algent_backend.agent_system.agents.review.spec import build_graph as build_reviewer
from algent_backend.agent_system.runs import events as ev
from algent_backend.agent_system.runs.context import AgentRunContext

from .contracts import GauntletReport

GAUNTLET_COMPLETED = "gauntlet.completed"
GAUNTLET_NO_INPUT = "gauntlet.no_input"

# The lanes to run, in deterministic order (sequential merge — see module docstring).
# Modules (not bound functions) so build_graph is resolved at call time.
_LANE_MODULES = [
    ("primary_source", primary_source),
    ("counter_perspective", counter_perspective),
]


class GauntletState(TypedDict, total=False):
    profile: dict[str, Any]   # the profile to put through the gauntlet (the input)
    gauntlet: dict[str, Any]  # the GauntletReport


def build_gauntlet_graph(context: AgentRunContext) -> Any:
    """Compile the gauntlet orchestrator graph."""

    def run_gauntlet(state: GauntletState, config: RunnableConfig) -> dict[str, Any]:
        profile = state.get("profile")
        if not profile:
            context.emit(GAUNTLET_NO_INPUT, {"message": "no profile supplied to the gauntlet"})
            return {"profile": profile or {}, "gauntlet": GauntletReport(final_verdict="unsound").model_dump()}

        start_rev = int(profile.get("revision", 1) or 1)

        # 1. review
        review = build_reviewer(context).invoke({"profile": profile}, config)["review"]
        _write(context, "review_initial.json", review)
        initial_verdict = review.get("verdict", "")
        initial_findings = len(review.get("findings", []))

        # 2-3. enrich per lane, sequentially — each merges on the prior result.
        from algent_backend.agent_system.agents.newsroom import budget_policy
        from algent_backend.agent_system.foundation.models.budget_gate import (
            BudgetRefusedError,
        )

        lanes_run: list[str] = []
        start_profile = profile
        initial_ids = {
            str(f.get("id")) for f in review.get("findings", []) if f.get("id")
        }
        for lane, module in _LANE_MODULES:
            if not any(f.get("lane") == lane for f in review.get("findings", [])):
                continue
            if not budget_policy.allow_optional("enrich_lane"):
                break
            try:
                out = module.build_graph(context).invoke(
                    {"profile": profile, "review": review}, config,
                )
            except BudgetRefusedError:
                # Soft/hard crossed mid-lane: keep what we have and stop enriching.
                break
            profile = out.get("profile", profile)
            lanes_run.append(lane)

        # 4. re-review only when enrichment ran or the profile revision moved. Skipping an
        # unchanged re-read saves a full review pass when there was nothing to re-judge.
        # Under slim_finish this re-pass is optional — keep the initial review and proceed
        # toward publish rather than dying on a refused model call.
        profile_changed = (
            int(profile.get("revision", start_rev) or start_rev) != start_rev
            or profile is not start_profile
        )
        if (lanes_run or profile_changed) and budget_policy.allow_optional(
            "gauntlet_rereview",
        ):
            try:
                rereview = build_reviewer(context).invoke(
                    {"profile": profile}, config,
                )["review"]
            except BudgetRefusedError:
                from algent_backend.agent_system.foundation import cost

                cost.record_skip("gauntlet_rereview", cost.mode())
                rereview = review
            _write(context, "review_final.json", rereview)
        else:
            rereview = review
            _write(context, "review_final.json", rereview)

        final_ids = {
            str(f.get("id")) for f in rereview.get("findings", []) if f.get("id")
        }
        # Re-review owns closure: findings present initially but absent after re-review.
        addressed = sorted(initial_ids - final_ids)

        report = GauntletReport(
            profile_id=str(profile.get("id", "")),
            starting_revision=start_rev,
            ending_revision=int(profile.get("revision", start_rev) or start_rev),
            lanes_run=lanes_run, findings_addressed=addressed,
            initial_verdict=initial_verdict, final_verdict=rereview.get("verdict", ""),
            initial_findings=initial_findings,
            remaining_findings=len(rereview.get("findings", [])),
            remaining_blockers=sum(1 for f in rereview.get("findings", []) if f.get("maturity_blocker")),
            generated_at=_now(),
        )
        if context.artifacts is not None:
            context.artifacts.write_json("profile.json", profile)
            context.artifacts.write_text("briefing.md", render_briefing(SignalProfile.model_validate(profile)))
            context.artifacts.write_json("gauntlet_report.json", report.model_dump())
        context.emit(ev.OUTPUT_PREVIEW, _preview(report))
        context.emit(GAUNTLET_COMPLETED, report.model_dump())
        return {"profile": profile, "gauntlet": report.model_dump()}

    graph = StateGraph(GauntletState)
    graph.add_node("gauntlet", run_gauntlet)
    graph.add_edge(START, "gauntlet")
    graph.add_edge("gauntlet", END)
    return graph.compile()


def _write(context: AgentRunContext, name: str, payload: Any) -> None:
    if context.artifacts is not None:
        context.artifacts.write_json(name, payload)


def _preview(report: GauntletReport) -> dict[str, Any]:
    return {
        "title": "profile gauntlet (1 round)",
        "summary": (
            f"{report.initial_verdict} (rev {report.starting_revision}) -> "
            f"{report.final_verdict} (rev {report.ending_revision}) | lanes {report.lanes_run} | "
            f"addressed {len(report.findings_addressed)} | remaining {report.remaining_findings} "
            f"findings ({report.remaining_blockers} blockers)"
        ),
        "items": [f"ran lane: {lane}" for lane in report.lanes_run],
        "link": "../artifacts/briefing.md",
    }


def _now() -> str:
    return datetime.now(UTC).isoformat()
