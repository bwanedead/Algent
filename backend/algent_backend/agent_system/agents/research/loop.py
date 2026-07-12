"""
The signal-profile loop — wraps the shared ReAct loop with vector->profile I/O.

Reads one selected signal vector, runs the research tool-calling loop (gated to the
agent's permitted channels + a hard paid budget + a USD cap), and emits the t2
``SignalProfile`` — persisting it both to the durable ``ProfileStore`` and as a run
artifact. Two things the harness owns (not the model): the profile's provenance/id,
and the tamper-evident source **snapshots** (captured during reads, attached here by
URL). LangGraph/LangChain imports live here; ``spec.py`` stays rail-free.
"""

from __future__ import annotations

from collections import Counter
from typing import Any, TypedDict

from langchain_core.messages import HumanMessage
from langchain_core.runnables import RunnableConfig
from langgraph.graph import END, START, StateGraph

from algent_backend.agent_system.agents.loop import build_react_loop, stream_react_loop
from algent_backend.agent_system.foundation import cost, snapshots
from algent_backend.agent_system.foundation.models import ModelSpec
from algent_backend.agent_system.runs import events as ev
from algent_backend.agent_system.runs.context import AgentRunContext
from algent_backend.agent_system.tools.sourcing.search import policy

from .assembly import finalize_profile
from .briefing import render_briefing
from .grounding import grounding_gap
from .leads import JsonLeadStore, backfeed_leads
from .messages import build_vector_message
from .profile import SignalProfile
from .store import JsonProfileStore

ARTIFACT_NAME = "profile.json"
BRIEFING_NAME = "briefing.md"
PROFILE_COMPLETED = "profile.completed"
PROFILE_NO_INPUT = "profile.no_input"
GROUNDING_CAPPED = "grounding.capped"   # the floor overrode the model's asserted maturity
GENERATOR = "signal_profile@v2"
STAGE = "signal_profile"


class ProfileState(TypedDict, total=False):
    vector: dict[str, Any]   # the selected signal vector to research (the input)
    profile: dict[str, Any]  # the produced t2 signal profile


def build_profile_graph(
    context: AgentRunContext,
    *,
    model_spec: ModelSpec,
    tool_ids: tuple[str, ...],
    system_prompt: str,
    search_channels: tuple[str, ...],
    paid_budget: int,
    cost_cap_usd: float,
) -> Any:
    """Compile the profile graph for an agent's model, tools, and gate."""
    model = context.model_resolver.resolve(model_spec).client
    tools = [context.tools[tool_id] for tool_id in tool_ids]
    agent = build_react_loop(model, tools, system_prompt=system_prompt, response_format=SignalProfile)

    def research(state: ProfileState, config: RunnableConfig) -> dict[str, Any]:
        vector = state.get("vector")
        if not vector:
            return _finish(context, SignalProfile(
                id="profile_none", title="(no vector)", profile_status="insufficient_evidence",
                summary="no signal vector supplied to research",
            ), event=PROFILE_NO_INPUT)

        context.emit(ev.INPUT_PREVIEW, _vector_preview(vector))

        # Scope the search gate + paid budget + USD cap, and collect source snapshots,
        # for the whole research loop.
        with policy.scoped(search_channels, paid_budget), \
                cost.scoped(cost_cap_usd, model_spec.model), snapshots.scoped():
            produced = stream_react_loop(
                agent,
                {"messages": [HumanMessage(content=build_vector_message(vector))]},
                context=context,
                config=config,
            )
            estimated_usd = cost.spent_usd()
            captured = snapshots.collected()

        if isinstance(produced, SignalProfile):
            profile = produced
        else:
            profile = SignalProfile(
                id="profile_unstructured", title=str(vector.get("title", ""))[:140],
                profile_status="insufficient_evidence",
                summary="model returned no structured profile",
            )

        asserted_status = profile.profile_status
        profile = finalize_profile(
            profile, vector, captured, model=model_spec.model, generator=GENERATOR, stage=STAGE
        )
        # Telemetry: the deterministic grounding floor overrode the model's maturity claim.
        # This is free doctrine-failure measurement AND the exact worklist enrichment can act on.
        if profile.profile_status != asserted_status:
            context.emit(GROUNDING_CAPPED, {
                "profile_id": profile.id, "asserted": asserted_status,
                "capped_to": profile.profile_status, "gap": grounding_gap(profile),
            })
        return _finish(context, profile, event=PROFILE_COMPLETED, estimated_usd=estimated_usd)

    graph = StateGraph(ProfileState)
    graph.add_node("research", research)
    graph.add_edge(START, "research")
    graph.add_edge("research", END)
    return graph.compile()


def _finish(
    context: AgentRunContext, profile: SignalProfile, *, event: str, estimated_usd: float = 0.0
) -> dict[str, Any]:
    # Persist to the durable store (the asset outlives the run) AND as run artifacts:
    # the canonical JSON plus the deterministic briefing VIEW a consuming agent reads.
    try:
        JsonProfileStore().save(profile)
    except Exception:  # noqa: BLE001 — a store hiccup must not fail an otherwise-good run
        pass
    # Backfeed: fold any adjacent leads this research noticed into the discovery queue (content-
    # addressed dedup + provenance), so the newsroom crowdsources its own organic ideas.
    if profile.derived_leads:
        backfeed_leads(profile.derived_leads, stage=STAGE, store=JsonLeadStore())
    link = None
    if context.artifacts is not None:
        context.artifacts.write_json(ARTIFACT_NAME, profile.model_dump())
        context.artifacts.write_text(BRIEFING_NAME, render_briefing(profile))
        link = "../artifacts/" + BRIEFING_NAME
    context.emit(ev.OUTPUT_PREVIEW, _profile_preview(profile, link))
    context.emit(event, {
        "profile_id": profile.id,
        "status": profile.profile_status,
        "claims": len(profile.claim_ledger),
        "threads": len(profile.threads),
        "sources": len(profile.source_ledger),
        "estimated_usd": estimated_usd,
    })
    return {"profile": profile.model_dump()}


def _profile_preview(profile: SignalProfile, link: str | None) -> dict[str, Any]:
    by_status = Counter(c.status for c in profile.claim_ledger)
    snapped = sum(1 for s in profile.source_ledger if s.snapshot is not None)
    return {
        "title": "t2 research profile",
        "summary": (
            f"status={profile.profile_status} | {len(profile.claim_ledger)} claims {dict(by_status)} | "
            f"{len(profile.threads)} threads | {len(profile.entities)} entities | "
            f"{len(profile.source_ledger)} sources ({snapped} snapshotted) | "
            f"{len(profile.derived_leads)} derived leads | recs={profile.output_recommendations}"
        ),
        "items": (
            [f"thread [{t.salience}/{t.kind or '?'}] {t.title[:80]}" for t in profile.threads[:8]]
            + [f"[{c.status}] {c.text[:80]}" for c in profile.claim_ledger[:6]]
        ),
        "link": link,
    }


def _vector_preview(vector: dict[str, Any]) -> dict[str, Any]:
    return {
        "title": "input: selected research vector",
        "summary": f"{vector.get('id', '?')} — {vector.get('title', '')}  [{vector.get('research_effort', '?')}]",
        "top": [f"thesis: {str(vector.get('thesis', ''))[:120]}"],
        "link": None,
    }
