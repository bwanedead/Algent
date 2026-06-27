"""
The signal-router run graph — the promotion router as a runnable agent (t1 -> t2).

A one-node graph: read a t1 signal portfolio from the run's initial state, rank it
with the promotion router, and select the #1 vector to promote. It writes two
artifacts — the full ranking and the selected vector — and the selected vector is the
input the signal-profile agent will consume next.

Run it in isolation on a saved portfolio with:
    runs start signal_router --fixture
LangGraph imports live here; spec.py stays rail-free.
"""

from __future__ import annotations

from typing import Any, TypedDict

from langchain_core.runnables import RunnableConfig
from langgraph.graph import END, START, StateGraph

from algent_backend.agent_system.agents.discovery.portfolio import ResearchPortfolio
from algent_backend.agent_system.foundation.models import ModelSpec
from algent_backend.agent_system.runs import events as ev
from algent_backend.agent_system.runs.context import AgentRunContext

from .contracts import RouteRanking
from .promotion import rank_portfolio, top_vector

ROUTING_NO_INPUT = "signal_router.no_input"
RANKING_ARTIFACT = "ranking.json"
SELECTION_ARTIFACT = "selected_vector.json"


class RouterState(TypedDict, total=False):
    portfolio: dict[str, Any]        # the t1 signal portfolio (the input to rank)
    ranking: dict[str, Any]          # the produced ranking
    selected_vector: dict[str, Any]  # the #1 vector — the profile agent's input


def build_signal_router_graph(context: AgentRunContext, *, model_spec: ModelSpec) -> Any:
    """Compile the signal-router graph for the given model."""

    def decide(state: RouterState, config: RunnableConfig) -> dict[str, Any]:
        portfolio_dict = state.get("portfolio")
        if not portfolio_dict:
            context.emit(ROUTING_NO_INPUT, {"message": "no portfolio in run input (feed one via --fixture / --input-key portfolio)"})
            return {"ranking": RouteRanking(note="no portfolio provided").model_dump()}

        portfolio = ResearchPortfolio.model_validate(portfolio_dict)
        ranking, by_id = rank_portfolio(context, portfolio, model_spec=model_spec, config=config)
        top = top_vector(ranking, by_id)

        link = None
        if context.artifacts is not None:
            context.artifacts.write_json(RANKING_ARTIFACT, ranking.model_dump())
            if top is not None:
                context.artifacts.write_json(SELECTION_ARTIFACT, top.model_dump())
                link = "../artifacts/" + SELECTION_ARTIFACT

        context.emit(ev.OUTPUT_PREVIEW, _ranking_preview(ranking, by_id, top, link))

        out: dict[str, Any] = {"ranking": ranking.model_dump()}
        if top is not None:
            out["selected_vector"] = top.model_dump()
        return out

    graph = StateGraph(RouterState)
    graph.add_node("decide", decide)
    graph.add_edge(START, "decide")
    graph.add_edge("decide", END)
    return graph.compile()


def _ranking_preview(ranking: RouteRanking, by_id: dict, top: Any, link: str | None) -> dict[str, Any]:
    """A timeline view: the ranked top-10 + the selection that promotes."""
    items = []
    for choice in ranking.choices[:10]:
        vec = by_id.get(choice.candidate_id)
        title = vec.title if vec is not None else choice.candidate_id
        items.append(f"#{choice.rank} [{choice.score}] {title[:58]} — {choice.rationale[:80]}")
    summary = (
        f"ranked {len(ranking.choices)} of {len(by_id)} vectors"
        + (f"; PROMOTING: {top.title}" if top is not None else "; no selection")
    )
    return {
        "title": "t1->t2 routing (ranked; #1 promotes to a profile)",
        "summary": summary,
        "items": items,
        "link": link,
    }
