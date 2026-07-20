"""
The editorial pipeline (v1) — profile -> planning gauntlet -> drafting gauntlet -> article.

One run turns a research profile into a finished article, chaining the two gauntlets that
already work as sub-graphs under one run/context (so every stage's events land in this run's
timeline). It does NOT hard-gate on the planning verdict — the drafter writes from the best
treatment available, and the article is always produced; the report carries the quality signals
(treatment verdict, draft outcome, walls caveated) that the eventual human approval surface
reads. The upstream research + profile gauntlet are separate, proven stages; prepend them to go
from a raw vector.
"""

from __future__ import annotations

import os
from datetime import UTC, datetime
from typing import Any, TypedDict

from langchain_core.runnables import RunnableConfig
from langgraph.graph import END, START, StateGraph

from algent_backend.agent_system.agents.research.profile import SignalProfile
from algent_backend.agent_system.runs import events as ev
from algent_backend.agent_system.runs.context import AgentRunContext

from .analytics_spec import build_graph as build_analytics_router
from .analytics_worker import build_analytics_worker_graph
from .caveat_spec import build_graph as build_caveat_reviewer
from .comprehension_spec import build_graph as build_comprehension_reviewer
from .draft import ArticleDraft
from .draft_gauntlet import build_drafting_gauntlet_graph
from .draft_spec import build_graph as build_drafter
from .draft_store import render_draft
from .gauntlet import build_planning_gauntlet_graph
from .headline_spec import build_graph as build_headline_writer
from .pipeline_contracts import EditorialPipelineReport
from .publish import render_published_article

PIPELINE_COMPLETED = "editorial_pipeline.completed"
PIPELINE_NO_INPUT = "editorial_pipeline.no_input"
CAVEAT_REPAIRED = "editorial_pipeline.caveat_repaired"   # the self-heal lap ran; here's the outcome
RAMP_REPAIRED = "editorial_pipeline.ramp_repaired"       # the comprehension repair lap ran

# The analytics WORKER (grok subprocess) is gated separately from the router. The router is cheap
# (a nano assessment, always runs); the worker is minutes-long and spends subscription quota per
# request, so it is OFF by default and capped — mirroring the ALGENT_RAKE toggle idiom. Flip the
# default once live pipeline runs prove it stable.
_ANALYTICS_WORKER_ENV = "ALGENT_ANALYTICS_WORKER"
_ANALYTICS_CAP_ENV = "ALGENT_ANALYTICS_MAX"
# Soft default was 3 and every live run filled it — padding. Prefer at most one strong analytic
# unless the operator raises the cap; zero is still success when nothing useful exists.
_ANALYTICS_CAP_DEFAULT = 1


def _analytics_worker_enabled() -> bool:
    return os.environ.get(_ANALYTICS_WORKER_ENV, "0").strip().lower() in ("1", "true", "yes", "on")


def _analytics_cap() -> int:
    try:
        return max(0, int(os.environ.get(_ANALYTICS_CAP_ENV, _ANALYTICS_CAP_DEFAULT)))
    except ValueError:
        return _ANALYTICS_CAP_DEFAULT


class PipelineState(TypedDict, total=False):
    profile: dict[str, Any]    # the research profile to turn into an article (input)
    treatment: dict[str, Any]  # the planned treatment
    draft: dict[str, Any]      # the finished article
    pipeline: dict[str, Any]   # the EditorialPipelineReport


def build_editorial_pipeline_graph(context: AgentRunContext) -> Any:
    """Compile the end-to-end editorial pipeline (profile -> article)."""

    def run(state: PipelineState, config: RunnableConfig) -> dict[str, Any]:
        profile = state.get("profile")
        if not profile:
            context.emit(PIPELINE_NO_INPUT, {"message": "no profile supplied to the editorial pipeline"})
            return {"pipeline": EditorialPipelineReport().model_dump()}

        # 1. plan (the planning gauntlet: plan -> review -> revise -> re-review).
        plan_out = build_planning_gauntlet_graph(context).invoke({"profile": profile}, config)
        treatment = plan_out.get("treatment") or {}
        plan_report = plan_out.get("gauntlet") or {}

        # 2. draft (the drafting gauntlet: draft -> audit -> revise until grounded/caveated).
        draft_out = build_drafting_gauntlet_graph(context).invoke(
            {"treatment": treatment, "profile": profile}, config)
        draft = draft_out.get("draft") or {}
        enriched_profile = draft_out.get("profile") or profile   # final grounding state for the appendix
        draft_report = draft_out.get("gauntlet") or {}

        # 3. headline — retitle from the FINAL prose, per headline-guidance.md (truthful, no clickbait).
        if draft:
            hl = build_headline_writer(context).invoke({"draft": draft}, config).get("headline") or {}
            if hl.get("title"):
                draft = {**draft, "title": hl["title"], "standfirst": hl.get("standfirst") or draft.get("standfirst", "")}

        # 4. v3b — verify the flagged promises are actually kept in the prose (the last honesty
        # gate). Cheap: nano, and free when nothing is flagged. Its pass is what earns "publishable".
        # Runs AFTER the headline because it judges title + standfirst + body.
        caveat = build_caveat_reviewer(context).invoke(
            {"draft": draft, "profile": enriched_profile}, config).get("caveat_check") or {}
        caveat_verdict = str(caveat.get("verdict", "verified"))

        # 4b. SELF-HEAL — one bounded repair lap (see _repair_hedging).
        caveat_rounds = 1
        if caveat_verdict == "needs_hedging" and draft:
            draft, enriched_profile, caveat, caveat_rounds = _repair_hedging(
                context, config, draft=draft, treatment=treatment, profile=enriched_profile, caveat=caveat)
            caveat_verdict = str(caveat.get("verdict", "verified"))

        # 4c. COMPREHENSION (gate C) — see _comprehension_pass. Advisory-with-repair, never a
        # publish gate: a hard-to-follow piece is a dud, not a lie, so it ships either way.
        draft, enriched_profile, comprehension, comprehension_rounds = _comprehension_pass(
            context, config, draft=draft, treatment=treatment, profile=enriched_profile)

        # 5. analytics routing — assess whether a chart/table/insight/illustration would make the
        # story clearer, emitting grounded requests (cheap nano; always runs).
        analytics = build_analytics_router(context).invoke(
            {"profile": enriched_profile}, config).get("analytics_plan") or {}

        # 6. analytics WORKER (gated + capped) — fulfill the grounded requests into real artifacts
        # via the sandboxed grok subprocess. OFF by default: each request is a minutes-long,
        # quota-spending run. When on, cap the batch and hand only the produced artifacts forward.
        produced_analytics: list[dict[str, Any]] = []
        if analytics.get("warranted") and _analytics_worker_enabled():
            capped = {**analytics, "requests": (analytics.get("requests") or [])[: _analytics_cap()]}
            produced_analytics = build_analytics_worker_graph(context).invoke(
                {"analytics_plan": capped, "profile": enriched_profile}, config).get("analytics_artifacts") or []

        outcome = str(draft_report.get("outcome", ""))
        if outcome == "blocked_omission":
            status = "blocked"                # dropped required evidence — a real block
        elif caveat_verdict == "needs_hedging":
            status = "needs_hedging"          # the prose doesn't keep a flagged promise — hold
        else:
            status = "publishable"            # grounded (or honestly caveated) AND caveats verified

        report = EditorialPipelineReport(
            profile_id=str(profile.get("id", "")),
            treatment_id=str(treatment.get("id", "")),
            treatment_verdict=str(plan_report.get("final_verdict", "")),
            draft_id=str(draft.get("id", "")),
            draft_outcome=outcome,
            publishable=status == "publishable",
            status=status,
            caveat_verdict=caveat_verdict,
            caveat_findings=len(caveat.get("findings", [])),
            caveat_rounds=caveat_rounds,
            comprehension_verdict=str(comprehension.get("verdict", "")),
            comprehension_findings=len(comprehension.get("findings", [])),
            comprehension_rounds=comprehension_rounds,
            article_title=str(draft.get("title", "")),
            word_count=int(draft.get("word_count", 0) or 0),
            barriers=draft_report.get("barriers", []),
            unverified_figures=draft_report.get("unverified_figures", []),
            analytics_warranted=bool(analytics.get("warranted")),
            analytics_count=len(analytics.get("requests", [])),
            analytics_produced=sum(1 for a in produced_analytics if a.get("status") == "produced"),
            analytics_escapes=sum(1 for a in produced_analytics if a.get("escaped_writes")),
            generated_at=datetime.now(UTC).isoformat(),
        )
        if context.artifacts is not None and draft:
            draft_obj = ArticleDraft.model_validate(draft)
            # The reader-facing piece + transparency appendix (with any produced charts embedded +
            # receipted), and the annotated draft for audit.
            context.artifacts.write_text(
                "article_published.md",
                render_published_article(
                    draft_obj, SignalProfile.model_validate(enriched_profile), produced_analytics))
            context.artifacts.write_text("article.md", render_draft(draft_obj))
            context.artifacts.write_json("editorial_pipeline_report.json", report.model_dump())
        context.emit(ev.OUTPUT_PREVIEW, _preview(report))
        context.emit(PIPELINE_COMPLETED, report.model_dump())
        return {"treatment": treatment, "draft": draft, "pipeline": report.model_dump()}

    graph = StateGraph(PipelineState)
    graph.add_node("pipeline", run)
    graph.add_edge(START, "pipeline")
    graph.add_edge("pipeline", END)
    return graph.compile()


def _repair_hedging(
    context: AgentRunContext, config: RunnableConfig, *,
    draft: dict[str, Any], treatment: dict[str, Any], profile: dict[str, Any], caveat: dict[str, Any],
) -> tuple[dict[str, Any], dict[str, Any], dict[str, Any], int]:
    """One bounded lap that repairs an overclaim instead of parking the piece.

    The caveat findings name specific sentences and specific problems, so the fix is surgical:
    hedge exactly those, re-headline (the title must stay truthful to the changed prose), re-check.
    This is what makes ``needs_hedging`` mean *took one more lap* rather than *held in a queue
    nobody reads* — duds ship by design, overclaims get repaired by machine, and nothing waits on a
    human. Bounded at one lap: if the repair doesn't take, we stay honest rather than loop.
    """
    repaired = build_drafter(context).invoke(
        {"treatment": treatment, "profile": profile, "prior_draft": draft, "caveat_check": caveat}, config)
    new_draft = repaired.get("draft") or {}
    if not new_draft:
        return draft, profile, caveat, 2          # the repair produced nothing; keep the honest verdict

    profile = repaired.get("profile") or profile
    hl = build_headline_writer(context).invoke({"draft": new_draft}, config).get("headline") or {}
    if hl.get("title"):
        new_draft = {**new_draft, "title": hl["title"],
                     "standfirst": hl.get("standfirst") or new_draft.get("standfirst", "")}
    rechecked = build_caveat_reviewer(context).invoke(
        {"draft": new_draft, "profile": profile}, config).get("caveat_check") or {}
    context.emit(CAVEAT_REPAIRED, {"verdict": rechecked.get("verdict"),
                                   "findings_remaining": len(rechecked.get("findings", []))})
    return new_draft, profile, rechecked, 2


def _comprehension_pass(
    context: AgentRunContext, config: RunnableConfig, *,
    draft: dict[str, Any], treatment: dict[str, Any], profile: dict[str, Any],
) -> tuple[dict[str, Any], dict[str, Any], dict[str, Any], int]:
    """Gate C: a general reader reads the prose COLD; if they stumble, one bounded ramp-repair lap.

    Advisory — a hard-to-follow piece ships anyway; this only tries to make it clearer first. The
    repair is handhold-or-cut only (adds no claims), so no honesty gate re-runs after it.
    """
    comprehension = build_comprehension_reviewer(context).invoke({"draft": draft}, config).get(
        "comprehension_check") or {}
    if str(comprehension.get("verdict", "clear")) != "needs_ramp" or not draft:
        return draft, profile, comprehension, 1
    return _repair_comprehension(context, config, draft=draft, treatment=treatment,
                                 profile=profile, comprehension=comprehension)


def _repair_comprehension(
    context: AgentRunContext, config: RunnableConfig, *,
    draft: dict[str, Any], treatment: dict[str, Any], profile: dict[str, Any], comprehension: dict[str, Any],
) -> tuple[dict[str, Any], dict[str, Any], dict[str, Any], int]:
    """One bounded ramp-repair lap: a general reader stumbled; add the flagged handholds or cut.

    Handhold-or-cut only (the drafter's comprehension block enforces it) — it adds no claims and
    strengthens nothing, so no honesty gate needs to re-run. If the repair produces nothing, keep
    the original draft and the honest verdict rather than looping.
    """
    repaired = build_drafter(context).invoke(
        {"treatment": treatment, "profile": profile, "prior_draft": draft,
         "comprehension_check": comprehension}, config)
    new_draft = repaired.get("draft") or {}
    if not new_draft:
        return draft, profile, comprehension, 2
    profile = repaired.get("profile") or profile
    rechecked = build_comprehension_reviewer(context).invoke({"draft": new_draft}, config).get(
        "comprehension_check") or {}
    context.emit(RAMP_REPAIRED, {"verdict": rechecked.get("verdict"),
                                 "findings_remaining": len(rechecked.get("findings", []))})
    return new_draft, profile, rechecked, 2


def _preview(r: EditorialPipelineReport) -> dict[str, Any]:
    return {
        "title": f"article: {r.article_title[:70] or '(untitled)'}",
        "summary": (
            f"{r.word_count} words | status: {r.status} | draft: {r.draft_outcome} | "
            f"caveats: {r.caveat_verdict}"
            + (f" ({r.caveat_findings} to fix)" if r.caveat_findings else "")
            + (f" | walls: {r.barriers}" if r.barriers else "")
        ),
        "items": [f"treatment: {r.treatment_id}", f"draft: {r.draft_id}"],
        "link": "../artifacts/article.md",
    }
