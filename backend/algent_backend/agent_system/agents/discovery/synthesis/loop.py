"""
The synthesis loop — wraps the shared ReAct loop with t0->t1 I/O.

Loads the t0 discovery pool, runs the model's tool-calling loop (gated to the
agent's permitted search channels and a hard paid-call budget for the duration),
and emits the t1 ``ResearchPortfolio`` as the run's artifact. LangGraph/LangChain
imports live here; the agent's ``spec.py`` stays rail-free.
"""

from __future__ import annotations

import json
from datetime import UTC, datetime
from typing import Any, TypedDict

from langchain_core.messages import HumanMessage
from langchain_core.runnables import RunnableConfig
from langgraph.graph import END, START, StateGraph

from algent_backend.agent_system.agents.discovery.portfolio import ResearchPortfolio
from algent_backend.agent_system.agents.loop import build_react_loop, stream_react_loop
from algent_backend.agent_system.foundation import cost
from algent_backend.agent_system.foundation.models import ModelSpec
from algent_backend.agent_system.runs import events as ev
from algent_backend.agent_system.runs.context import AgentRunContext
from algent_backend.agent_system.tools.sourcing.search import policy

from .messages import build_t0_message

ARTIFACT_NAME = "research_portfolio.json"
SYNTHESIS_COMPLETED = "synthesis.completed"
SYNTHESIS_NO_T0 = "synthesis.no_t0"
SYNTHESIS_NO_STRUCTURED_OUTPUT = "synthesis.no_structured_output"


class SynthesisState(TypedDict, total=False):
    pool: dict[str, Any]  # the t0 payload; loaded from disk if absent
    portfolio: dict[str, Any]


def build_synthesis_graph(
    context: AgentRunContext,
    *,
    model_spec: ModelSpec,
    tool_ids: tuple[str, ...],
    system_prompt: str,
    search_channels: tuple[str, ...],
    paid_budget: int,
    cost_cap_usd: float,
) -> Any:
    """Compile the synthesis graph for an agent's model, tools, and gate."""
    model = context.model_resolver.resolve(model_spec).client
    tools = [context.tools[tool_id] for tool_id in tool_ids]
    agent = build_react_loop(model, tools, system_prompt=system_prompt, response_format=ResearchPortfolio)

    def synthesize(state: SynthesisState, config: RunnableConfig) -> dict[str, Any]:
        pool = state.get("pool")
        pool_path: str | None = None
        if not pool:
            pool, pool_path = _load_latest_pool()
        if not pool:
            return _finish(context, ResearchPortfolio(
                generated_at=_now(),
                dropped_note=(
                    "no t0 pool found — produce one first: `ingest insights gdelt_gkg "
                    "--warmup 6`, `ingest pool`, then re-run."
                ),
            ), event=SYNTHESIS_NO_T0)

        # Surface a curated preview of the t0 input in the timeline, with a link
        # to the full pool file — so a watcher sees what the agent received.
        context.emit(ev.INPUT_PREVIEW, _t0_preview(pool, pool_path))

        # Scope the search gate + paid-call budget + USD cost cap to this run for
        # its whole duration. The cost meter auto-halts the loop if spend caps out.
        with policy.scoped(search_channels, paid_budget), cost.scoped(cost_cap_usd, model_spec.model):
            produced = stream_react_loop(
                agent,
                {"messages": [HumanMessage(content=build_t0_message(pool))]},
                context=context,
                config=config,
            )
            estimated_usd = cost.spent_usd()

        if isinstance(produced, ResearchPortfolio):
            portfolio = produced
        else:
            context.emit(SYNTHESIS_NO_STRUCTURED_OUTPUT, {"raw_type": type(produced).__name__})
            portfolio = ResearchPortfolio(
                generated_at=_now(), dropped_note="model returned no structured portfolio"
            )
        portfolio = portfolio.model_copy(update={
            "generated_at": portfolio.generated_at or _now(),
            "t0_ref": portfolio.t0_ref or pool.get("gkg_batch_id") or pool.get("generated_at"),
            "total_considered": pool.get("item_count", len(pool.get("items", []))),
        })
        return _finish(context, portfolio, event=SYNTHESIS_COMPLETED, estimated_usd=estimated_usd)

    graph = StateGraph(SynthesisState)
    graph.add_node("synthesize", synthesize)
    graph.add_edge(START, "synthesize")
    graph.add_edge("synthesize", END)
    return graph.compile()


def _finish(
    context: AgentRunContext,
    portfolio: ResearchPortfolio,
    *,
    event: str,
    estimated_usd: float = 0.0,
) -> dict[str, Any]:
    if context.artifacts is not None:
        context.artifacts.write_json(ARTIFACT_NAME, portfolio.model_dump())
    context.emit(event, {"vector_count": len(portfolio.vectors), "estimated_usd": estimated_usd})
    return {"portfolio": portfolio.model_dump()}


def _load_latest_pool() -> tuple[dict[str, Any] | None, str | None]:
    """Read the most recent t0 pool artifact: returns (pool, path), (None, None)."""
    from algent_backend.data_ingestion.cli._shared import latest_file, pool_dir

    path = latest_file(pool_dir(), "pool_*.json")
    if path is None:
        return None, None
    try:
        return json.loads(path.read_text(encoding="utf-8")), str(path)
    except (OSError, ValueError):
        return None, None


def _t0_preview(pool: dict[str, Any], pool_path: str | None) -> dict[str, Any]:
    """A curated, top-hits preview of the t0 pool for the timeline (+ a link)."""
    items = pool.get("items", [])
    top = sorted(items, key=lambda i: (i.get("signals") or {}).get("score") or 0, reverse=True)
    return {
        "title": "t0 discovery pool",
        "summary": (
            f"{pool.get('item_count', len(items))} items | "
            f"channels {pool.get('by_channel', {})} | pillars {pool.get('by_pillar', {})}"
        ),
        "top": [
            f"{i.get('label', '')[:48]}  [{i.get('kind', '?')}]"
            f"  {','.join(i.get('pillars', [])) or '-'}"
            for i in top[:12]
        ],
        "link": pool_path,
    }


def _now() -> str:
    return datetime.now(UTC).isoformat()
