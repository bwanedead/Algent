"""
The headline-writer loop — draft -> Headline. Tool-free, one structured call on the nano tier.
"""

from __future__ import annotations

from typing import Any, TypedDict

from langchain_core.messages import HumanMessage, SystemMessage
from langchain_core.runnables import RunnableConfig
from langgraph.graph import END, START, StateGraph

from algent_backend.agent_system.foundation.models import ModelSpec
from algent_backend.agent_system.runs.context import AgentRunContext

from .draft import ArticleDraft
from .headline_contracts import Headline
from .headline_messages import build_headline_message
from .headline_prompts import SYSTEM_PROMPT

HEADLINE_COMPLETED = "headline.completed"


class HeadlineState(TypedDict, total=False):
    draft: dict[str, Any]     # the finished draft (input)
    headline: dict[str, Any]  # the produced Headline


def build_headline_writer_graph(context: AgentRunContext, *, model_spec: ModelSpec) -> Any:
    model = context.model_resolver.resolve(model_spec).client
    structured = model.with_structured_output(Headline)

    def write(state: HeadlineState, config: RunnableConfig) -> dict[str, Any]:
        ddict = state.get("draft")
        if not ddict:
            return {"headline": Headline().model_dump()}
        draft = ArticleDraft.model_validate(ddict)
        raw = structured.invoke(
            [SystemMessage(content=SYSTEM_PROMPT), HumanMessage(content=build_headline_message(draft))],
            config=config,
        )
        headline = raw if isinstance(raw, Headline) else Headline(title=draft.title, standfirst=draft.standfirst)
        context.emit(HEADLINE_COMPLETED, {"draft_id": draft.id, "title": headline.title})
        return {"headline": headline.model_dump()}

    graph = StateGraph(HeadlineState)
    graph.add_node("write", write)
    graph.add_edge(START, "write")
    graph.add_edge("write", END)
    return graph.compile()
