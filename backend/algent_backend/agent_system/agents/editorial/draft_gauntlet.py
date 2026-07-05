"""
The drafting gauntlet (v3a) — draft -> audit -> revise until grounded (deterministic gate).

    draft -> check_citations -> [if not grounded: revise with the worklist -> re-audit]* -> report

The gate is the deterministic citation harness — NO judgment tokens. When a draft isn't
`grounded`, the drafter is sent back with the exact lists (the deep-read worklist AND the
dropped must-use items, so both are fixed in one round), reads the flagged sources in full,
which upgrades their grounding on the enrich-back merge, and the re-audit clears the floor.
Bounded rounds; a still-ungrounded final verdict is a valid, honest outcome.

v3b (the semantic multi-lens reviewer — frame held, hedging fidelity, perspective symmetry)
bolts onto this working gate later, downstream of the harness.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any, TypedDict

from langchain_core.runnables import RunnableConfig
from langgraph.graph import END, START, StateGraph

from algent_backend.agent_system.runs import events as ev
from algent_backend.agent_system.runs.context import AgentRunContext

from .draft_gauntlet_contracts import DraftingGauntletReport
from .draft_spec import build_graph as build_drafter

GAUNTLET_COMPLETED = "drafting_gauntlet.completed"
GAUNTLET_NO_INPUT = "drafting_gauntlet.no_input"
MAX_ROUNDS = 3  # initial + up to 2 revisions — bounded; the loop exits early once grounded


class GauntletState(TypedDict, total=False):
    treatment: dict[str, Any]  # the promoted treatment to draft from (input)
    profile: dict[str, Any]    # its source profile (input; enriched as reads land)
    draft: dict[str, Any]      # the final draft
    gauntlet: dict[str, Any]   # the DraftingGauntletReport


def build_drafting_gauntlet_graph(context: AgentRunContext) -> Any:
    """Compile the drafting-gauntlet orchestrator graph."""

    def run_gauntlet(state: GauntletState, config: RunnableConfig) -> dict[str, Any]:
        treatment, profile = state.get("treatment"), state.get("profile")
        if not treatment or not profile:
            context.emit(GAUNTLET_NO_INPUT, {"message": "treatment or profile missing to the drafting gauntlet"})
            return {"gauntlet": DraftingGauntletReport(final_verdict="drops_must_use").model_dump()}

        # Round 1: draft + audit.
        out = build_drafter(context).invoke({"treatment": treatment, "profile": profile}, config)
        draft, profile, report = out["draft"], out["profile"], out["citation_report"]
        _write(context, "draft_round1.json", draft)
        initial_verdict = report["verdict"]
        initial_weak = len(report.get("weak_load_bearing", []))

        # Revise while the deterministic floor isn't cleared (bounded). The drafter is driven by
        # the report's LISTS, not the masked verdict — worklist + missing fixed in one pass.
        rounds = 1
        while report["verdict"] != "grounded" and rounds < MAX_ROUNDS:
            out = build_drafter(context).invoke(
                {"treatment": treatment, "profile": profile,
                 "prior_draft": draft, "citation_report": report}, config)
            draft, profile, report = out["draft"], out["profile"], out["citation_report"]
            rounds += 1
            _write(context, f"draft_round{rounds}.json", draft)

        result = DraftingGauntletReport(
            treatment_id=str(draft.get("treatment_id", "")),
            profile_id=str(draft.get("profile_id", "")),
            draft_id=str(draft.get("id", "")),
            rounds=rounds,
            promoted=report["verdict"] == "grounded",
            initial_verdict=initial_verdict, final_verdict=report["verdict"],
            initial_weak_claims=initial_weak,
            final_weak_claims=len(report.get("weak_load_bearing", [])),
            final_must_use_missing=len(report.get("must_use_missing", [])),
            final_worklist=report.get("deep_read_worklist", []),
            ending_profile_revision=int(profile.get("revision", 1) or 1),
            generated_at=datetime.now(UTC).isoformat(),
        )
        if context.artifacts is not None:
            context.artifacts.write_json("draft.json", draft)
            context.artifacts.write_json("drafting_gauntlet_report.json", result.model_dump())
        context.emit(ev.OUTPUT_PREVIEW, _preview(result))
        context.emit(GAUNTLET_COMPLETED, result.model_dump())
        return {"draft": draft, "gauntlet": result.model_dump()}

    graph = StateGraph(GauntletState)
    graph.add_node("gauntlet", run_gauntlet)
    graph.add_edge(START, "gauntlet")
    graph.add_edge("gauntlet", END)
    return graph.compile()


def _write(context: AgentRunContext, name: str, payload: Any) -> None:
    if context.artifacts is not None:
        context.artifacts.write_json(name, payload)


def _preview(r: DraftingGauntletReport) -> dict[str, Any]:
    return {
        "title": f"drafting gauntlet ({r.rounds} round(s))",
        "summary": (
            f"{r.initial_verdict} -> {r.final_verdict} | promoted: {r.promoted} | "
            f"weak claims {r.initial_weak_claims} -> {r.final_weak_claims} | "
            f"profile rev {r.ending_profile_revision}"
            + (f" | still unread: {r.final_worklist}" if r.final_worklist else "")
        ),
        "items": [f"draft: {r.draft_id}", f"rounds: {r.rounds}"],
        "link": "../artifacts/draft.json",
    }
