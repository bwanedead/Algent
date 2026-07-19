"""
The comprehension-reviewer loop — draft -> ComprehensionCheck (the naive-reader lane, gate C).

Tool-free, one nano judgment over the PROSE ALONE. Unlike the caveat lane there is no deterministic
worklist to short-circuit on — comprehension is only visible by reading — so it always makes the
(cheap) call when there is prose to read. It receives no profile and no treatment BY DESIGN: a
reviewer that can see what the piece meant cannot judge whether it landed.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any, TypedDict

from langchain_core.messages import HumanMessage, SystemMessage
from langchain_core.runnables import RunnableConfig
from langgraph.graph import END, START, StateGraph

from algent_backend.agent_system.foundation.models import ModelSpec
from algent_backend.agent_system.runs.context import AgentRunContext

from .comprehension_contracts import ComprehensionCheck
from .comprehension_prompts import SYSTEM_PROMPT
from .draft import ArticleDraft

ARTIFACT_NAME = "comprehension_check.json"
COMPREHENSION_COMPLETED = "comprehension_check.completed"
COMPREHENSION_SKIPPED = "comprehension_check.skipped"
GENERATOR = "comprehension_reviewer@v1"


class ComprehensionState(TypedDict, total=False):
    draft: dict[str, Any]              # the finished draft to read cold (input) — NO profile by design
    comprehension_check: dict[str, Any]


def _message(draft: ArticleDraft) -> str:
    """Only the reader-facing prose — title, standfirst, body. No ids, no evidence, no plan."""
    return "\n\n".join(x for x in (
        f"TITLE: {draft.title}", f"STANDFIRST: {draft.standfirst}", draft.body.strip(),
        "TASK: Read this as its intended general reader and report only where you genuinely "
        "stumbled — an unexplained load-bearing term, an assumed context, an island paragraph, or "
        "where you lost the thread. Your only fixes are a handhold or a cut. If it reads clearly, "
        "return 'clear' with no findings.",
    ) if x)


def build_comprehension_reviewer_graph(context: AgentRunContext, *, model_spec: ModelSpec) -> Any:
    """Compile the comprehension-reviewer graph (no tools — one cold read of the prose)."""
    model = context.model_resolver.resolve(model_spec).client
    structured = model.with_structured_output(ComprehensionCheck)

    def review(state: ComprehensionState, config: RunnableConfig) -> dict[str, Any]:
        ddict = state.get("draft")
        draft = ArticleDraft.model_validate(ddict) if ddict else None
        if draft is None or not draft.body.strip():
            return _finish(context, ComprehensionCheck(id="comprehension_none", verdict="clear",
                                                       summary="no prose to read"), skipped=True)

        raw = structured.invoke(
            [SystemMessage(content=SYSTEM_PROMPT), HumanMessage(content=_message(draft))],
            config=config,
        )
        check = raw if isinstance(raw, ComprehensionCheck) else ComprehensionCheck(
            id="", verdict="clear", summary="reviewer returned no structured check")
        return _finish(context, _finalize(check, draft, model_spec.model))

    graph = StateGraph(ComprehensionState)
    graph.add_node("review", review)
    graph.add_edge(START, "review")
    graph.add_edge("review", END)
    return graph.compile()


def _finalize(check: ComprehensionCheck, draft: ArticleDraft, model: str) -> ComprehensionCheck:
    findings = [f if f.id else f.model_copy(update={"id": f"cmp_{i:02d}"})
                for i, f in enumerate(check.findings, 1)]
    # A structured check with findings but a stale/clear verdict is coerced honest.
    verdict = "needs_ramp" if findings else check.verdict
    return check.model_copy(update={
        "id": f"comprehension_{draft.id}", "draft_id": draft.id, "findings": findings,
        "verdict": verdict, "reviewer": GENERATOR, "model": model,
        "generated_at": datetime.now(UTC).isoformat(),
    })


def _finish(context: AgentRunContext, check: ComprehensionCheck, *, skipped: bool = False) -> dict[str, Any]:
    if context.artifacts is not None:
        context.artifacts.write_json(ARTIFACT_NAME, check.model_dump())
    context.emit(COMPREHENSION_SKIPPED if skipped else COMPREHENSION_COMPLETED, {
        "draft_id": check.draft_id, "verdict": check.verdict, "findings": len(check.findings),
    })
    return {"comprehension_check": check.model_dump()}
