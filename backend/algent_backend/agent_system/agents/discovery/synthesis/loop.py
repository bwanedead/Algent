"""
The synthesis loop — wraps the shared ReAct loop with t0->t1 I/O.

Loads the t0 discovery pool, runs the model's tool-calling loop (gated to the
agent's permitted search channels and a hard paid-call budget for the duration),
and emits the t1 ``ResearchPortfolio`` as the run's artifact. LangGraph/LangChain
imports live here; the agent's ``spec.py`` stays rail-free.
"""

from __future__ import annotations

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
from algent_backend.data_ingestion.news_production.discovery.pipeline import ensure_t0

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
        # Self-source t0: produce (or reuse a fresh) discovery pool right here, so
        # starting the run is the only step — no manual ingest first. Narrated to
        # the timeline via t0.progress events; free (GDELT bulk).
        pool = state.get("pool")
        if not pool:
            try:
                pool, _ = ensure_t0(
                    on_progress=lambda m: context.emit(ev.T0_PROGRESS, {"message": m})
                )
            except Exception as exc:  # noqa: BLE001 — a GDELT outage is a run result, not a crash
                return _finish(context, ResearchPortfolio(
                    generated_at=_now(), dropped_note=f"t0 production failed: {exc}"
                ), event=SYNTHESIS_NO_T0)

        # Snapshot t0 INTO this run so it stays auditable (and linkable) even after
        # the shared pool file is purged by a later run. Link relatively from the
        # timeline (audit/timeline.md -> artifacts/t0_pool.json) so it clicks in-IDE.
        t0_link: str | None = None
        if context.artifacts is not None:
            context.artifacts.write_json("t0_pool.json", pool)
            t0_link = "../artifacts/t0_pool.json"

        # Curated preview of the t0 input in the timeline, with a link to the snapshot.
        context.emit(ev.INPUT_PREVIEW, _t0_preview(pool, t0_link))

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
    link = None
    if context.artifacts is not None:
        context.artifacts.write_json(ARTIFACT_NAME, portfolio.model_dump())
        link = "../artifacts/" + ARTIFACT_NAME
    # Curated full output in the timeline — every vector (one line), so the human
    # sees them all, not just the truncated model text, plus a link to the full t1.
    if portfolio.vectors:
        context.emit(ev.OUTPUT_PREVIEW, _t1_preview(portfolio, link))
    context.emit(event, {"vector_count": len(portfolio.vectors), "estimated_usd": estimated_usd})
    return {"portfolio": portfolio.model_dump()}


def _t1_preview(portfolio: ResearchPortfolio, link: str | None) -> dict[str, Any]:
    """A clean one-line-per-vector view of the t1 portfolio for the timeline."""
    return {
        "title": "t1 research portfolio",
        "summary": f"{len(portfolio.vectors)} vectors from {portfolio.total_considered} t0 hits",
        "items": [
            f"{i}. {v.title}  [{v.vector_type}/{v.research_effort}]  "
            f"hits={v.supporting_hits}  sources={len(v.sources)}"
            for i, v in enumerate(portfolio.vectors, 1)
        ],
        "link": link,
    }


def _t0_preview(pool: dict[str, Any], link: str | None) -> dict[str, Any]:
    """A top-by-rank sample of the t0 pool for the timeline (+ a link to the full list)."""
    items = pool.get("items", [])
    top = sorted(items, key=lambda i: (i.get("signals") or {}).get("score") or 0, reverse=True)
    return {
        "title": "t0 discovery pool (top-ranked sample — full list linked below)",
        "summary": (
            f"{pool.get('item_count', len(items))} items | "
            f"channels {pool.get('by_channel', {})} | pillars {pool.get('by_pillar', {})}"
        ),
        "top": [
            f"{i.get('label', '')[:46]}  [{i.get('kind', '?')}]"
            f"  {','.join(i.get('pillars', [])) or '-'}"
            f"  score={(i.get('signals') or {}).get('score', '-')}"
            for i in top[:15]
        ],
        "link": link,
    }


def _now() -> str:
    return datetime.now(UTC).isoformat()
