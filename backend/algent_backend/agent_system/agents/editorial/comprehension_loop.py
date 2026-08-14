"""
The comprehension-reviewer loop — draft -> ComprehensionCheck (the naive-reader lane, gate C).

Tool-free, one cold read of the PROSE ALONE. When the piece does not land, the same call emits
the next draft (title/standfirst/body). Unlike the caveat lane there is no deterministic
worklist to short-circuit on — comprehension is only visible by reading. It receives no profile
and no treatment BY DESIGN: a reviewer that can see what the piece meant cannot judge whether
it landed, and a rewrite from the page cannot grow new claims.
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
GENERATOR = "comprehension_reviewer@v2"


class ComprehensionState(TypedDict, total=False):
    draft: dict[str, Any]              # the finished draft to read cold (input) — NO profile by design
    places: list[str]                  # country flags assigned to this piece, for the reviewer to judge
    comprehension_check: dict[str, Any]


def _message(draft: ArticleDraft, places: list[str] | None = None) -> str:
    """Only the reader-facing prose — title, standfirst, body. No ids, no evidence, no plan.

    Plus the country flags the page will carry. Those are reader-facing furniture, and this is
    the first stage that can see both them and the finished prose, so it is the only stage that
    can tell whether the piece earns them.
    """
    flags_block = (
        "COUNTRY FLAGS THIS PAGE WILL SHOW: " + ", ".join(places)
        + "\nJudge each one from the prose alone: does the piece make clear why this country is "
          "part of the story? Reporting FROM a country, or an agency that happens to be based "
          "there, is not the same as the story being ABOUT it."
        if places else ""
    )
    return "\n\n".join(x for x in (
        f"TITLE: {draft.title}", f"STANDFIRST: {draft.standfirst}", draft.body.strip(),
        flags_block,
        "TASK: Read this as its intended general reader (cold, not following the story day to day). "
        "Report only where you genuinely stumbled. If it does not land, emit the next draft in "
        "title/standfirst/body — same facts, digestible grain, no new claims. Leave those empty "
        "when clear.\n"
        "FRIEND TEST (required): After reading, could you explain to a friend — using only this "
        "prose — (1) what happened / was found, (2) why it matters, (3) what the underlying "
        "dispute/situation is, (4) who wants what, (5) what remains open? If you only hold vague "
        "residue, that is needs_ramp: flag missing_news_kernel / vague_conflict / missing_scene "
        "/ assumed_context / opening_order as fits, and write the piece that would pass.\n"
        "Also flag jargon_before_gloss, unclear_causal_chain, method_before_payoff, lecture, "
        "wall_of_text, "
        "and announced_importance machine-slop ('That first fact matters because…', "
        "'this sets the frame', 'put plainly') — cut those in the rewrite.\n"
        "If the friend test passes and it reads clearly, return 'clear' with no findings and "
        "empty title/standfirst/body.",
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

        places = [str(p) for p in (state.get("places") or [])]
        raw = structured.invoke(
            [SystemMessage(content=SYSTEM_PROMPT),
             HumanMessage(content=_message(draft, places))],
            config=config,
        )
        check = raw if isinstance(raw, ComprehensionCheck) else ComprehensionCheck(
            id="", verdict="clear", summary="reviewer returned no structured check")
        return _finish(context, _finalize(check, draft, model_spec.model, places=places))

    graph = StateGraph(ComprehensionState)
    graph.add_node("review", review)
    graph.add_edge(START, "review")
    graph.add_edge("review", END)
    return graph.compile()


def _finalize(
    check: ComprehensionCheck, draft: ArticleDraft, model: str,
    *, places: list[str] | None = None,
) -> ComprehensionCheck:
    findings = [f if f.id else f.model_copy(update={"id": f"cmp_{i:02d}"})
                for i, f in enumerate(check.findings, 1)]

    # Only flags we actually showed it can be dropped. A model naming a country that was
    # never assigned is confused, and honouring that would let a review invent removals —
    # the same reason the flags come from the declared contract and not a lexical scan.
    offered = {p.strip().casefold() for p in (places or [])}
    drops = [p for p in check.places_to_drop if p.strip().casefold() in offered]

    # A dropped flag is a resolved problem, not an outstanding one: the fix is applied at
    # publish, so it must not by itself force a repair lap on the prose.
    open_findings = [f for f in findings
                     if not (f.kind == "unjustified_flag"
                             and f.where.strip().casefold() in
                             {d.strip().casefold() for d in drops})]
    verdict = "needs_ramp" if open_findings else check.verdict
    return check.model_copy(update={
        "id": f"comprehension_{draft.id}", "draft_id": draft.id, "findings": findings,
        "places_to_drop": drops,
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
