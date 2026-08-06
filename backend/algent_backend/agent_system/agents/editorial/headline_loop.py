"""
The headline-writer loop — draft (+ optional treatment) -> Headline.
Tool-free, one structured call on the nano tier.
"""

from __future__ import annotations

from typing import Any, TypedDict

from langchain_core.messages import HumanMessage, SystemMessage
from langchain_core.runnables import RunnableConfig
from langgraph.graph import END, START, StateGraph

from algent_backend.agent_system.foundation.models import ModelSpec
from algent_backend.agent_system.foundation.models.budget_gate import gate_chat_model
from algent_backend.agent_system.runs.context import AgentRunContext

from .draft import ArticleDraft
from .headline_contracts import Headline
from .headline_messages import build_headline_message
from .headline_prompts import SYSTEM_PROMPT
from .treatment import EditorialTreatment

HEADLINE_COMPLETED = "headline.completed"


class HeadlineState(TypedDict, total=False):
    draft: dict[str, Any]         # the finished draft (input)
    treatment: dict[str, Any]     # optional planned entry fields
    surface_issues: list[str]     # optional cold-browser repair notes
    headline: dict[str, Any]      # the produced Headline


def build_headline_writer_graph(context: AgentRunContext, *, model_spec: ModelSpec) -> Any:
    # Finish-path one-shot: mark the gated client essential so slim_finish still admits it
    # without wrapping tools in cost.essential_scope.
    model = gate_chat_model(
        context.model_resolver.resolve(model_spec).client, essential=True,
    )
    structured = model.with_structured_output(Headline)

    def write(state: HeadlineState, config: RunnableConfig) -> dict[str, Any]:
        ddict = state.get("draft")
        if not ddict:
            return {"headline": Headline().model_dump()}
        draft = ArticleDraft.model_validate(ddict)
        treatment = None
        if state.get("treatment"):
            try:
                treatment = EditorialTreatment.model_validate(state["treatment"])
            except Exception:  # noqa: BLE001 — surface package still runs without treatment
                treatment = None
        issues = [str(x) for x in (state.get("surface_issues") or []) if x]
        raw = structured.invoke(
            [SystemMessage(content=SYSTEM_PROMPT),
             HumanMessage(content=build_headline_message(
                 draft, treatment, surface_issues=issues or None))],
            config=config,
        )
        headline = raw if isinstance(raw, Headline) else Headline(
            title=draft.title, standfirst=draft.standfirst, quick_take=draft.quick_take)
        context.emit(HEADLINE_COMPLETED, {"draft_id": draft.id, "title": headline.title})
        return {"headline": headline.model_dump()}

    graph = StateGraph(HeadlineState)
    graph.add_node("write", write)
    graph.add_edge(START, "write")
    graph.add_edge("write", END)
    return graph.compile()
