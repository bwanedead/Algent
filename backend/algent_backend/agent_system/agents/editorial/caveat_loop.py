"""
The caveat-reviewer loop — (draft, profile) -> CaveatCheck.

Tool-free: one structured-output judgment over the prose + the deterministic worklists. If there
is nothing to check (no flagged promises), it short-circuits to a `verified` check with no model
call at all — so the lane costs nothing on a cleanly-grounded piece.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any, TypedDict

from langchain_core.messages import HumanMessage, SystemMessage
from langchain_core.runnables import RunnableConfig
from langgraph.graph import END, START, StateGraph

from algent_backend.agent_system.agents.research.profile import SignalProfile
from algent_backend.agent_system.foundation.models import ModelSpec
from algent_backend.agent_system.runs.context import AgentRunContext

from .caveat_contracts import CaveatCheck
from .caveat_messages import build_caveat_message, caveat_worklists, has_promises_to_check
from .caveat_prompts import SYSTEM_PROMPT
from .draft import ArticleDraft

ARTIFACT_NAME = "caveat_check.json"
CAVEAT_COMPLETED = "caveat_check.completed"
CAVEAT_SKIPPED = "caveat_check.skipped"
GENERATOR = "caveat_reviewer@v1"


class CaveatState(TypedDict, total=False):
    draft: dict[str, Any]         # the finished draft to check (input)
    profile: dict[str, Any]       # its source profile (input — for claim grades/grounding)
    caveat_check: dict[str, Any]  # the produced CaveatCheck


def build_caveat_reviewer_graph(context: AgentRunContext, *, model_spec: ModelSpec) -> Any:
    """Compile the caveat-reviewer graph (no tools — pure judgment over the flagged list)."""
    model = context.model_resolver.resolve(model_spec).client
    structured = model.with_structured_output(CaveatCheck)

    def review(state: CaveatState, config: RunnableConfig) -> dict[str, Any]:
        ddict, pdict = state.get("draft"), state.get("profile")
        if not ddict or not pdict:
            return _finish(context, CaveatCheck(id="caveat_none", verdict="verified",
                                                summary="no draft/profile supplied"), skipped=True)
        draft = ArticleDraft.model_validate(ddict)
        profile = SignalProfile.model_validate(pdict)

        # Nothing flagged -> nothing to verify. No model call.
        if not has_promises_to_check(caveat_worklists(draft, profile)):
            return _finish(context, CaveatCheck(id=f"caveat_{draft.id}", draft_id=draft.id,
                                                verdict="verified", summary="no promises to check"),
                           skipped=True)

        raw = structured.invoke(
            [SystemMessage(content=SYSTEM_PROMPT),
             HumanMessage(content=build_caveat_message(draft, profile))],
            config=config,
        )
        check = raw if isinstance(raw, CaveatCheck) else CaveatCheck(id="", verdict="needs_hedging",
                                                                     summary="reviewer returned no structured check")
        return _finish(context, _finalize(check, draft, model_spec.model))

    graph = StateGraph(CaveatState)
    graph.add_node("review", review)
    graph.add_edge(START, "review")
    graph.add_edge("review", END)
    return graph.compile()


def _finalize(check: CaveatCheck, draft: ArticleDraft, model: str) -> CaveatCheck:
    findings = [f if f.id else f.model_copy(update={"id": f"cav_{i:02d}"})
                for i, f in enumerate(check.findings, 1)]
    return check.model_copy(update={
        "id": f"caveat_{draft.id}", "draft_id": draft.id, "findings": findings,
        "reviewer": GENERATOR, "model": model, "generated_at": datetime.now(UTC).isoformat(),
    })


def _finish(context: AgentRunContext, check: CaveatCheck, *, skipped: bool = False) -> dict[str, Any]:
    if context.artifacts is not None:
        context.artifacts.write_json(ARTIFACT_NAME, check.model_dump())
    context.emit(CAVEAT_SKIPPED if skipped else CAVEAT_COMPLETED, {
        "draft_id": check.draft_id, "verdict": check.verdict, "findings": len(check.findings),
    })
    return {"caveat_check": check.model_dump()}
