"""
The full newsroom rail (v1) — raw discovery pool -> finished, receipted article, one run.

    [backfeed intake] -> synthesis -> routing -> profile -> profile gauntlet -> editorial pipeline

It chains the stages that already work as sub-graphs under ONE run/context (the same idiom the
gauntlets and the editorial pipeline use), so every stage's events land in this run's timeline and
a single report closes the loop. Three deliberate properties:

  (i)   COST — the rail tees the event stream and sums each stage's reported ``estimated_usd``, so
        every finished article carries what it actually cost to make.
  (ii)  BOUNDED — the rail inherits each stage's own floors (models, paid budgets, USD caps, review
        gates); it re-litigates none of them. It promotes the router's single #1 vector — one article
        per run — rather than fanning out.
  (iii) BACKFEED — before discovery, it reads the damped open leads (``open_leads_for_discovery``)
        and merges them into the t0 pool, so the leads the research loop emits actually re-enter
        discovery. The damping cap is applied on the intake side; consumed leads are marked so they
        do not loop forever.

Each stage can legitimately be the end: no promotable vector is a valid outcome, not an error.
"""

from __future__ import annotations

import dataclasses
import os
from datetime import UTC, datetime
from typing import Any, TypedDict

from langchain_core.runnables import RunnableConfig
from langgraph.graph import END, START, StateGraph

from algent_backend.agent_system.agents.research.leads import (
    JsonLeadStore,
    open_leads_for_discovery,
)
from algent_backend.agent_system.runs import events as ev
from algent_backend.agent_system.runs.context import AgentRunContext

from ..discovery.synthesis.spec import build_graph as build_synthesis
from ..editorial.pipeline_spec import build_graph as build_editorial
from ..gauntlet.spec import build_graph as build_profile_gauntlet
from ..research.spec import build_graph as build_profile
from ..routing.spec import build_graph as build_router
from .rail_contracts import NewsroomRailReport

RAIL_COMPLETED = "newsroom_rail.completed"
RAIL_STAGE = "newsroom_rail.stage"
BACKFEED_INJECTED = "newsroom_rail.backfeed_injected"

# The backfeed read-side is ON by default — the loop only closes if the leads actually re-enter
# discovery. ALGENT_BACKFEED=0 turns it off; ALGENT_BACKFEED_MAX caps how many leads enter (the
# damping cap on the intake side).
_BACKFEED_ENV = "ALGENT_BACKFEED"
_BACKFEED_CAP_ENV = "ALGENT_BACKFEED_MAX"
_BACKFEED_CAP_DEFAULT = 5

# Where a backfed lead sits relative to fresh t0 signal: present and competing, but never
# dominating a genuinely hot story (top t0 scores run ~7+). Confidence sets the rung.
_LEAD_SCORE = {"high": 5.0, "med": 3.0, "medium": 3.0, "low": 1.5, "": 2.0}


def _backfeed_enabled() -> bool:
    return os.environ.get(_BACKFEED_ENV, "1").strip().lower() not in ("0", "false", "no", "off")


def _backfeed_cap() -> int:
    try:
        return max(0, int(os.environ.get(_BACKFEED_CAP_ENV, _BACKFEED_CAP_DEFAULT)))
    except ValueError:
        return _BACKFEED_CAP_DEFAULT


class RailState(TypedDict, total=False):
    pool: dict[str, Any]       # optional t0 pool; synthesis self-sources if absent
    rail: dict[str, Any]       # the NewsroomRailReport
    pipeline: dict[str, Any]   # the editorial pipeline's report (the article)


def build_newsroom_rail_graph(context: AgentRunContext, *, lead_store: Any | None = None) -> Any:
    """Compile the full-rail orchestrator. ``lead_store`` is injectable (tests pass a fake)."""

    def run(state: RailState, config: RunnableConfig) -> dict[str, Any]:
        # (i) COST tee — a context whose emit forwards to the real sink AND captures every stage's
        # reported estimated_usd, so the rail can total the run's spend.
        costs: list[float] = []

        def _tee(event_type: str, payload: dict[str, Any] | None = None) -> None:
            p = payload or {}
            usd = p.get("estimated_usd")
            if isinstance(usd, (int, float)):
                costs.append(float(usd))
            context.emit(event_type, p)

        sub = dataclasses.replace(context, emit=_tee)
        report = NewsroomRailReport(generated_at=datetime.now(UTC).isoformat())

        # (iii) BACKFEED intake — merge the damped open leads into the discovery pool.
        pool = state.get("pool")
        if _backfeed_enabled():
            pool, injected = _inject_backfeed(context, pool, lead_store or JsonLeadStore())
            report.backfeed_leads_injected = injected

        # 1. discovery synthesis (pool -> t1 portfolio). No pool -> synthesis self-sources t0.
        context.emit(RAIL_STAGE, {"stage": "synthesis"})
        syn_input: dict[str, Any] = {"pool": pool} if pool is not None else {}
        portfolio = build_synthesis(sub).invoke(syn_input, config).get("portfolio") or {}
        report.vector_count = len(portfolio.get("vectors", []))
        report.pool_items = int(portfolio.get("total_considered", 0) or 0)
        report.stage_reached = "synthesis"
        if not portfolio.get("vectors"):
            return _finish(context, report, note="synthesis produced no vectors")

        # 2. routing (portfolio -> the #1 vector to promote).
        context.emit(RAIL_STAGE, {"stage": "routing"})
        route = build_router(sub).invoke({"portfolio": portfolio}, config)
        vector = route.get("selected_vector")
        report.stage_reached = "routing"
        if not vector:
            return _finish(context, report, note="routing promoted no vector")
        report.selected_vector_id = str(vector.get("id", ""))
        report.selected_vector_title = str(vector.get("title", ""))

        # 3. profile (the #1 vector -> a researched t2 profile).
        context.emit(RAIL_STAGE, {"stage": "profile"})
        profile = build_profile(sub).invoke({"vector": vector}, config).get("profile") or {}
        report.stage_reached = "profile"
        if not profile.get("id"):
            return _finish(context, report, note="profile research produced nothing")
        report.profile_id = str(profile.get("id", ""))

        # 4. profile gauntlet (review/enrich the profile to maturity).
        context.emit(RAIL_STAGE, {"stage": "gauntlet"})
        g = build_profile_gauntlet(sub).invoke({"profile": profile}, config)
        profile = g.get("profile") or profile
        report.gauntlet_verdict = str((g.get("gauntlet") or {}).get("final_verdict", ""))
        report.stage_reached = "gauntlet"

        # 5. editorial pipeline (profile -> planned, drafted, headlined, caveated, receipted article).
        context.emit(RAIL_STAGE, {"stage": "editorial"})
        pipeline = build_editorial(sub).invoke({"profile": profile}, config).get("pipeline") or {}
        report.article_status = str(pipeline.get("status", ""))
        report.article_title = str(pipeline.get("article_title", ""))
        report.analytics_produced = int(pipeline.get("analytics_produced", 0) or 0)
        report.stage_reached = "complete"

        return _finish(context, report, pipeline=pipeline, total=round(sum(costs), 6))

    graph = StateGraph(RailState)
    graph.add_node("run", run)
    graph.add_edge(START, "run")
    graph.add_edge("run", END)
    return graph.compile()


def _inject_backfeed(context: AgentRunContext, pool: dict | None, store: Any) -> tuple[dict | None, int]:
    """Read the damped open leads and merge them into the t0 pool as items. Returns (pool, count).

    If there is no pool yet, we source t0 here (the same ``ensure_t0`` synthesis would call) so the
    backfed leads ride alongside fresh discovery rather than replacing it. Consumed leads are marked
    so a lead cannot re-enter discovery run after run.
    """
    try:
        leads = open_leads_for_discovery(store, limit=_backfeed_cap())
    except Exception as exc:  # noqa: BLE001 — a lead-store hiccup must not sink the whole run
        context.emit(BACKFEED_INJECTED, {"error": str(exc)[:180], "injected": 0})
        return pool, 0
    if not leads:
        return pool, 0

    if pool is None:
        from algent_backend.data_ingestion.newsroom.discovery.pipeline import ensure_t0
        try:
            pool, _ = ensure_t0(on_progress=lambda m: context.emit(ev.T0_PROGRESS, {"message": m}))
        except Exception as exc:  # noqa: BLE001 — no fresh t0 is fine; leads still seed discovery
            context.emit(ev.T0_PROGRESS, {"message": f"t0 unavailable, seeding from leads only: {exc}"})
            pool = {"items": [], "item_count": 0}

    items = list(pool.get("items", []))
    have = {i.get("id") for i in items}
    new = [it for le in leads if (it := _lead_to_item(le))["id"] not in have]
    merged = {**pool, "items": items + new, "item_count": int(pool.get("item_count", len(items))) + len(new)}

    for le in leads:
        try:
            store.mark_consumed(le.id)   # consume so the lead does not loop forever
        except Exception:  # noqa: BLE001 — best-effort; a failed consume just risks one re-look
            pass
    context.emit(BACKFEED_INJECTED, {"injected": len(new), "considered": len(leads)})
    return merged, len(new)


def _lead_to_item(lead: Any) -> dict[str, Any]:
    """A backfed DerivedLead as a t0 pool item — clearly channel='backfeed', never pre-vetted."""
    conf = str(getattr(lead, "confidence", "") or "").strip().lower()
    return {
        "id": f"backfeed:{lead.id}",
        "label": lead.title,
        "channel": "backfeed",
        "kind": "lead",
        "pillars": [],
        "scope": [],
        "signals": {"score": _LEAD_SCORE.get(conf, _LEAD_SCORE[""]), "rising": False,
                    "novel": True, "count": 1, "backfeed": True},
        "evidence": ([{"title": lead.title, "url": lead.source_url}] if getattr(lead, "source_url", "") else []),
        "related": list(dict.fromkeys([*getattr(lead, "entities", []), *getattr(lead, "topics", [])])),
    }


def _finish(
    context: AgentRunContext, report: NewsroomRailReport, *,
    pipeline: dict | None = None, total: float = 0.0, note: str = "",
) -> dict[str, Any]:
    if note:
        report.note = note
    report.total_usd = total
    if context.artifacts is not None:
        context.artifacts.write_json("newsroom_rail_report.json", report.model_dump())
    context.emit(ev.OUTPUT_PREVIEW, _preview(report))
    context.emit(RAIL_COMPLETED, report.model_dump())
    return {"rail": report.model_dump(), "pipeline": pipeline or {}}


def _preview(r: NewsroomRailReport) -> dict[str, Any]:
    return {
        "title": f"full rail -> {r.stage_reached}",
        "summary": (
            f"{r.pool_items} t0 items (+{r.backfeed_leads_injected} backfed) -> {r.vector_count} vectors"
            + (f" -> promoted: {r.selected_vector_title[:50]}" if r.selected_vector_title else "")
            + (f" -> article: {r.article_status}" if r.article_status else "")
            + f"  ·  ~${r.total_usd:.4f}"
            + (f"  ·  {r.note}" if r.note else "")
        ),
        "items": [
            f"profile: {r.profile_id or '—'} ({r.gauntlet_verdict or 'n/a'})",
            f"article: {r.article_title or '—'}",
        ],
        "link": "../artifacts/article_published.md",
    }
