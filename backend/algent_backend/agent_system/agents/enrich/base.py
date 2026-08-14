"""
The enrichment engine — generic gauntlet machinery, specialized per lane.

An enricher reads an existing profile + its ReviewReport, picks the findings for ITS lane,
researches them, and returns ADDITIVE items — which the merge harness folds in (revision++).
Identical at every lane; only the injected doctrine + the lane name differ (same pattern as
the generic router). LangGraph/LangChain imports live here; lane spec.py modules stay rail-free.
"""

from __future__ import annotations

from typing import Any, TypedDict

from langchain_core.messages import HumanMessage
from langchain_core.runnables import RunnableConfig
from langgraph.graph import END, START, StateGraph

from algent_backend.agent_system.agents.loop import build_react_loop, stream_react_loop
from algent_backend.agent_system.agents.research.assembly import merge_additions
from algent_backend.agent_system.agents.research.briefing import render_briefing
from algent_backend.agent_system.agents.research.profile import ProfileAdditions, SignalProfile
from algent_backend.agent_system.agents.research.store import JsonProfileStore
from algent_backend.agent_system.agents.review.contracts import ReviewReport
from algent_backend.agent_system.foundation import cost, snapshots
from algent_backend.agent_system.foundation.models import ModelSpec
from algent_backend.agent_system.runs import events as ev
from algent_backend.agent_system.runs.context import AgentRunContext

from .messages import build_enrich_message

ENRICH_COMPLETED = "enrich.completed"
ENRICH_NO_WORK = "enrich.no_work"
_SEVERITY_RANK = {"blocking": 0, "high": 1, "medium": 2, "low": 3}
_MAX_FINDINGS = 4  # bound the work per enrich pass


class EnrichState(TypedDict, total=False):
    profile: dict[str, Any]  # the profile to enrich
    review: dict[str, Any]   # its ReviewReport (the assignments)
    addressed: list[str]     # finding ids closed only after a validated evidence delta


def build_enrich_graph(
    context: AgentRunContext, *, lane: str, model_spec: ModelSpec, tool_ids: tuple[str, ...],
    system_prompt: str, search_channels: tuple[str, ...], paid_budget: int, cost_cap_usd: float,
) -> Any:
    """Compile an enrichment graph for one lane."""
    model = context.model_resolver.resolve(model_spec).client
    tools = [context.tools[tool_id] for tool_id in tool_ids]
    agent = build_react_loop(model, tools, system_prompt=system_prompt, response_format=ProfileAdditions)
    generator, stage = f"enrich_{lane}@v1", f"{lane}_enricher"

    def enrich(state: EnrichState, config: RunnableConfig) -> dict[str, Any]:
        pdict = state.get("profile")
        if not pdict:
            context.emit(ENRICH_NO_WORK, {"message": "no profile supplied to enrich"})
            return {"profile": pdict or {}, "addressed": []}
        profile = SignalProfile.model_validate(pdict)
        review = ReviewReport.model_validate(state["review"]) if state.get("review") else None
        findings = _select_findings(review, lane)
        if not findings:
            context.emit(ENRICH_NO_WORK, {"message": f"no '{lane}' findings to act on", "profile_id": profile.id})
            return {"profile": profile.model_dump(), "addressed": []}

        context.emit(ev.INPUT_PREVIEW, _assignment_preview(profile, findings, lane))
        with policy_scope(search_channels, paid_budget), cost.scoped(cost_cap_usd, model_spec.model), snapshots.scoped():
            produced = stream_react_loop(
                agent, {"messages": [HumanMessage(content=build_enrich_message(profile, findings, lane))]},
                context=context, config=config,
            )
            captured = snapshots.collected()
            estimated_usd = cost.spent_usd()   # capture inside the scope (it resets on exit)
        if not isinstance(produced, ProfileAdditions):
            # Loop aborted (budget or a rejected request). Do not bump revision
            # as if this lane ran — the model never finished additions.
            context.emit(ENRICH_NO_WORK, {
                "message": f"'{lane}' loop ended without additions",
                "profile_id": profile.id,
                "estimated_usd": estimated_usd,
            })
            return {"profile": profile.model_dump(), "addressed": []}
        additions = produced

        before = (len(profile.source_ledger), len(profile.claim_ledger), len(profile.threads))
        merged = merge_additions(profile, additions, captured, generator=generator, stage=stage)
        # Model-claimed closure is not authoritative — re-review owns finding closure.
        # Keep claimed ids on the event for observability; return none as "addressed".
        addressed: list[str] = []
        try:
            JsonProfileStore().save(merged)
        except Exception:  # noqa: BLE001
            pass
        if context.artifacts is not None:
            context.artifacts.write_json("profile.json", merged.model_dump())
            context.artifacts.write_text("briefing.md", render_briefing(merged))
        context.emit(ev.OUTPUT_PREVIEW, _enrich_preview(merged, before, additions, lane, addressed))
        context.emit(ENRICH_COMPLETED, {
            "profile_id": merged.id, "lane": lane, "revision": merged.revision,
            "added_sources": len(merged.source_ledger) - before[0],
            "added_claims": len(merged.claim_ledger) - before[1],
            "addressed": addressed,
            "addressed_claimed": additions.addressed_findings,
            "estimated_usd": estimated_usd,
        })
        return {"profile": merged.model_dump(), "addressed": addressed}

    graph = StateGraph(EnrichState)
    graph.add_node("enrich", enrich)
    graph.add_edge(START, "enrich")
    graph.add_edge("enrich", END)
    return graph.compile()


def policy_scope(channels, budget):
    from algent_backend.agent_system.tools.sourcing.search import policy
    return policy.scoped(channels, budget)


def _select_findings(review: ReviewReport | None, lane: str) -> list:
    if review is None:
        return []
    lane_findings = [f for f in review.findings if f.lane == lane]
    lane_findings.sort(key=lambda f: (not f.maturity_blocker, _SEVERITY_RANK.get(f.severity, 2)))
    return lane_findings[:_MAX_FINDINGS]


def _assignment_preview(profile: SignalProfile, findings: list, lane: str) -> dict[str, Any]:
    return {
        "title": f"enrichment assignment — lane: {lane}",
        "summary": f"profile {profile.id} (rev {profile.revision}) — {len(findings)} {lane} findings to address",
        "top": [f"[{f.severity}] {f.target}: {f.explanation[:90]}" for f in findings],
        "link": None,
    }


def _enrich_preview(
    merged: SignalProfile, before: tuple, additions: ProfileAdditions, lane: str,
    addressed: list[str] | None = None,
) -> dict[str, Any]:
    snap = sum(1 for s in merged.source_ledger if s.snapshot is not None)
    kept = addressed if addressed is not None else additions.addressed_findings
    return {
        "title": f"profile enriched (lane: {lane}, rev {merged.revision})",
        "summary": (
            f"+{len(merged.source_ledger) - before[0]} sources (+{snap} deep-read total), "
            f"+{len(merged.claim_ledger) - before[1]} claims, +{len(merged.threads) - before[2]} threads | "
            f"addressed: {kept}"
        ),
        "items": [f"+source: {s.title or s.url}" for s in additions.sources[:6]],
        "link": "../artifacts/briefing.md",
    }
