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
from datetime import UTC, datetime
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

from .messages import build_vector_message
from .profile import SignalProfile, SourceSnapshot
from .store import JsonProfileStore

ARTIFACT_NAME = "profile.json"
PROFILE_COMPLETED = "profile.completed"
PROFILE_NO_INPUT = "profile.no_input"
GENERATOR = "signal_profile@v1"


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

        profile = _finalize(profile, vector, captured, model_spec.model)
        return _finish(context, profile, event=PROFILE_COMPLETED, estimated_usd=estimated_usd)

    graph = StateGraph(ProfileState)
    graph.add_node("research", research)
    graph.add_edge(START, "research")
    graph.add_edge("research", END)
    return graph.compile()


def _finalize(
    profile: SignalProfile, vector: dict[str, Any], captured: dict[str, dict], model: str
) -> SignalProfile:
    """Harness-owned: attach snapshots by URL, stamp provenance + a stable id."""
    # The harness is the SOLE authority on snapshots — a model can't hash content, so
    # any model-provided snapshot is discarded. A source gets the real captured
    # snapshot (read via our tool) or none at all.
    for source in profile.source_ledger:
        captured_snap = captured.get(source.url) if source.url else None
        source.snapshot = SourceSnapshot(**captured_snap) if captured_snap else None
    return profile.model_copy(update={
        "id": _profile_id(vector),
        "parent_vector_id": vector.get("id", ""),
        "generated_at": _now(),
        "generator": GENERATOR,
        "model": model,
    })


def _finish(
    context: AgentRunContext, profile: SignalProfile, *, event: str, estimated_usd: float = 0.0
) -> dict[str, Any]:
    # Persist to the durable store (the asset outlives the run) AND as a run artifact.
    try:
        JsonProfileStore().save(profile)
    except Exception:  # noqa: BLE001 — a store hiccup must not fail an otherwise-good run
        pass
    link = None
    if context.artifacts is not None:
        context.artifacts.write_json(ARTIFACT_NAME, profile.model_dump())
        link = "../artifacts/" + ARTIFACT_NAME
    context.emit(ev.OUTPUT_PREVIEW, _profile_preview(profile, link))
    context.emit(event, {
        "profile_id": profile.id,
        "status": profile.profile_status,
        "claims": len(profile.claim_ledger),
        "sources": len(profile.source_ledger),
        "estimated_usd": estimated_usd,
    })
    return {"profile": profile.model_dump()}


def _profile_preview(profile: SignalProfile, link: str | None) -> dict[str, Any]:
    by_status = Counter(c.status for c in profile.claim_ledger)
    snapped = sum(1 for s in profile.source_ledger if s.snapshot is not None)
    return {
        "title": "t2 signal profile",
        "summary": (
            f"status={profile.profile_status} | {len(profile.claim_ledger)} claims {dict(by_status)} | "
            f"{len(profile.source_ledger)} sources ({snapped} snapshotted) | "
            f"{len(profile.derived_leads)} derived leads | recs={profile.output_recommendations}"
        ),
        "items": [
            f"[{c.status}] {c.text[:84]}  ←{','.join(c.supported_by) or '-'}"
            for c in profile.claim_ledger[:12]
        ],
        "link": link,
    }


def _vector_preview(vector: dict[str, Any]) -> dict[str, Any]:
    return {
        "title": "input: selected signal vector",
        "summary": f"{vector.get('id', '?')} — {vector.get('title', '')}  [{vector.get('research_effort', '?')}]",
        "top": [f"thesis: {str(vector.get('thesis', ''))[:120]}"],
        "link": None,
    }


def _profile_id(vector: dict[str, Any]) -> str:
    vid = str(vector.get("id") or "")
    return "prof_" + (vid.removeprefix("vec_") or "unknown")


def _now() -> str:
    return datetime.now(UTC).isoformat()
