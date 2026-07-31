"""
The editorial pipeline (v1) — profile -> planning gauntlet -> drafting gauntlet -> article.

One run turns a research profile into a finished article, chaining the two gauntlets that
already work as sub-graphs under one run/context (so every stage's events land in this run's
timeline). Soft quality signals (treatment verdict, thin_spine, needs_hedging) ride on the
report — they diagnose, they do not skip drafting. Bounded repair laps then hand off so the
site can be the review surface. Hard-stop only on mechanical impossibility (no profile).
"""

from __future__ import annotations

import os
from datetime import UTC, datetime
from typing import Any, TypedDict

from langchain_core.runnables import RunnableConfig
from langgraph.graph import END, START, StateGraph

from algent_backend.agent_system.agents.newsroom import budget_policy
from algent_backend.agent_system.agents.research.profile import SignalProfile
from algent_backend.agent_system.foundation import cost
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
from .hero_stage import make_hero
from .pipeline_contracts import EditorialPipelineReport
from .publish import render_published_article

PIPELINE_COMPLETED = "editorial_pipeline.completed"
PIPELINE_NO_INPUT = "editorial_pipeline.no_input"
CAVEAT_REPAIRED = "editorial_pipeline.caveat_repaired"   # the self-heal lap ran; here's the outcome
RAMP_REPAIRED = "editorial_pipeline.ramp_repaired"       # the comprehension repair lap ran
HERO_IMAGE = "editorial_pipeline.hero_image"             # hero generated / skipped, with the reason

# The analytics WORKER (grok subprocess) is gated separately from the router. The router is cheap
# (a nano assessment, always runs); the worker spends quota per request. ON by default so
# geography maps and trajectory charts actually ship — live runs with worker off planned
# figures that never appeared (Houthi choke-point, Wildberries strike map). Disable with
# ALGENT_ANALYTICS_WORKER=0. Cap still bounds cost.
_ANALYTICS_WORKER_ENV = "ALGENT_ANALYTICS_WORKER"
_ANALYTICS_CAP_ENV = "ALGENT_ANALYTICS_MAX"
# Prefer at most two strong analytics (e.g. theater map + trajectory). Zero is still success
# when nothing useful exists; three+ was padding.
_ANALYTICS_CAP_DEFAULT = 2

# A live failure mode: the comprehension "handhold" repair lap rewrote a ~400-word piece into a
# single sentence, then the pipeline still marked it publishable. A hollow shell is not a dud —
# it is a corrupted repair. Floor below this → not publishable; repair that collapses the body
# is discarded.
#: How many read→fix laps an article gets. The full sequence is:
#:
#:     draft → review → draft → review → draft → publish
#:
#: Two, and the bound is the point. Review cannot be open-ended: an unpublished article
#: teaches us nothing, the live site is the review surface, and a loop with no floor has no
#: reason to ever terminate — each read can always find something. The way quality improves is
#: not more laps; it is the register growing so the PRODUCTION stages stop generating these
#: defects at all.
#:
#: Note the sequence ends on a FIX, not a read. A final review whose verdict cannot change
#: whether the piece ships is spend with no consequence attached, so it is not performed — the
#: cheap mechanical collapse guard in ``_repair_once`` still protects that last repair.
_MAX_REVIEW_LAPS = 2

_MIN_PUBLISH_WORDS = 120
_REPAIR_KEEP_FRAC = 0.55  # keep prior draft if the repair keeps less than this share of body words


def _analytics_worker_enabled() -> bool:
    # Default ON — maps/charts are high reader value when the router warrants them.
    return os.environ.get(_ANALYTICS_WORKER_ENV, "1").strip().lower() in ("1", "true", "yes", "on")


def _analytics_cap() -> int:
    try:
        return max(0, int(os.environ.get(_ANALYTICS_CAP_ENV, _ANALYTICS_CAP_DEFAULT)))
    except ValueError:
        return _ANALYTICS_CAP_DEFAULT


def _body_words(draft: dict[str, Any] | None) -> int:
    if not draft:
        return 0
    body = str(draft.get("body") or "")
    n = len(body.split())
    if n:
        return n
    try:
        return int(draft.get("word_count") or 0)
    except (TypeError, ValueError):
        return 0


def _has_article_spine(profile: dict[str, Any] | None) -> bool:
    """True when the profile carries enough deep-read evidence to support an article.

    Citation grounding can pass on one podcast page; that proves the draft quoted its sources,
    not that there is a story. Require a snapshotted primary, or at least two snapshotted
    sources — the mechanical floor that separates a grounded stub from publishable prose.
    """
    if not profile:
        return False
    ledger = profile.get("source_ledger") or []
    snapshotted = [s for s in ledger if isinstance(s, dict) and s.get("snapshot")]
    if any(str(s.get("source_type") or "") == "primary" for s in snapshotted):
        return True
    return len(snapshotted) >= 2


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
            context.emit(
                PIPELINE_NO_INPUT,
                {"message": "no profile supplied to the editorial pipeline"},
            )
            return {"pipeline": EditorialPipelineReport().model_dump()}

        plan_out = build_planning_gauntlet_graph(context).invoke({"profile": profile}, config)
        treatment = plan_out.get("treatment") or {}
        plan_report = plan_out.get("gauntlet") or {}
        treatment = _ensure_treatment(treatment, profile)

        draft_out = build_drafting_gauntlet_graph(context).invoke(
            {"treatment": treatment, "profile": profile}, config)
        draft = draft_out.get("draft") or {}
        enriched_profile = draft_out.get("profile") or profile
        draft_report = draft_out.get("gauntlet") or {}

        # Hard stop with no draft: persist best artifacts and exit without spending more.
        if cost.is_hard_stop() and not draft.get("id"):
            report = EditorialPipelineReport(
                profile_id=str(profile.get("id", "")),
                status="hard_cost_cap",
                generated_at=datetime.now(UTC).isoformat(),
            )
            if context.artifacts is not None:
                context.artifacts.write_json("editorial_pipeline_report.json", report.model_dump())
            context.emit(PIPELINE_COMPLETED, report.model_dump())
            return {"treatment": treatment, "draft": draft, "pipeline": report.model_dump()}

        draft, hero = _headline_and_hero(context, config, draft)

        caveat = build_caveat_reviewer(context).invoke(
            {"draft": draft, "profile": enriched_profile}, config).get("caveat_check") or {}
        caveat_verdict = str(caveat.get("verdict", "verified"))
        caveat_rounds = 1
        if caveat_verdict == "needs_hedging" and draft:
            if budget_policy.allow_optional("draft_repair"):
                draft, enriched_profile, caveat, caveat_rounds = _repair_hedging(
                    context, config, draft=draft, treatment=treatment,
                    profile=enriched_profile, caveat=caveat)
                caveat_verdict = str(caveat.get("verdict", "verified"))
            else:
                caveat_rounds = 1

        assigned_places = _derive_places(enriched_profile)
        if budget_policy.allow_optional("comprehension_repair"):
            draft, enriched_profile, comprehension, comprehension_rounds = _comprehension_pass(
                context, config, draft=draft, treatment=treatment, profile=enriched_profile,
                places=assigned_places)
        else:
            comprehension, comprehension_rounds = {}, 0

        if budget_policy.allow_optional("analytics"):
            analytics = build_analytics_router(context).invoke(
                {"profile": enriched_profile}, config).get("analytics_plan") or {}
            produced_analytics = _run_analytics_worker(
                context, config, analytics, enriched_profile)
        else:
            analytics, produced_analytics = {}, []

        outcome = str(draft_report.get("outcome", ""))
        words = _body_words(draft)
        if draft:
            draft = {**draft, "word_count": words}
        status = _pipeline_status(outcome, caveat_verdict, words, enriched_profile)
        if cost.is_hard_stop() and draft.get("id"):
            status = "cost_capped"

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
            places_to_drop=[str(p) for p in (comprehension.get("places_to_drop") or [])],
            hero=hero,
            article_title=str(draft.get("title", "")),
            word_count=words,
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


def _ensure_treatment(treatment: dict[str, Any], profile: dict[str, Any]) -> dict[str, Any]:
    if treatment.get("id"):
        return treatment
    return {
        **treatment,
        "id": f"trt_fallback_{profile.get('id', 'x')}",
        "revision": 1,
        "reader_question": "What can be said honestly from the available evidence?",
    }


def _headline_and_hero(
    context: AgentRunContext, config: RunnableConfig, draft: dict[str, Any],
) -> tuple[dict[str, Any], dict[str, Any] | None]:
    hero: dict[str, Any] | None = None
    if not draft:
        return draft, hero
    with cost.essential_scope():
        hl = build_headline_writer(context).invoke({"draft": draft}, config).get("headline") or {}
        if hl.get("title"):
            draft = {
                **draft,
                "title": hl["title"],
                "standfirst": hl.get("standfirst") or draft.get("standfirst", ""),
            }
        hero = make_hero(hl, context.artifacts, say=lambda m: context.emit(HERO_IMAGE, {"note": m}))
    return draft, hero


def _run_analytics_worker(
    context: AgentRunContext, config: RunnableConfig,
    analytics: dict[str, Any], profile: dict[str, Any],
) -> list[dict[str, Any]]:
    if not (analytics.get("warranted") and _analytics_worker_enabled()):
        return []
    capped = {**analytics, "requests": (analytics.get("requests") or [])[: _analytics_cap()]}
    return build_analytics_worker_graph(context).invoke(
        {"analytics_plan": capped, "profile": profile}, config,
    ).get("analytics_artifacts") or []


def _pipeline_status(
    outcome: str, caveat_verdict: str, words: int, profile: dict[str, Any] | None,
) -> str:
    if outcome == "blocked_omission":
        return "blocked"
    if caveat_verdict == "needs_hedging":
        return "needs_hedging"
    if words < _MIN_PUBLISH_WORDS:
        return "needs_revision"
    if not _has_article_spine(profile):
        return "thin_spine"
    return "publishable"


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


def _derive_places(profile: dict[str, Any]) -> list[str]:
    """The country flags this piece would fly, so the reviewer can judge them against the prose.

    Uses the same derivation publish uses, so what the reviewer judges is exactly what a reader
    would see — geography comes from the profile's declared contract and nothing else.
    """
    from algent_backend.publishing.tagging import derive_places

    try:
        places, _flags = derive_places(profile or {})
    except Exception:  # noqa: BLE001 — flags are furniture; never fail an article over them
        return []
    return places


def _comprehension_pass(
    context: AgentRunContext, config: RunnableConfig, *,
    draft: dict[str, Any], treatment: dict[str, Any], profile: dict[str, Any],
    places: list[str] | None = None,
) -> tuple[dict[str, Any], dict[str, Any], dict[str, Any], int]:
    """The review stage: read the finished prose COLD, send it back to be fixed, bounded.

    The sequence is **draft → review → draft → review → draft → publish**. Two reads, each
    followed by a repair, and then it ships. Note what deliberately does NOT happen: the last
    repair is not re-reviewed. A review whose verdict cannot change the outcome is spend with
    no consequence attached, so the loop ends on a fix rather than on an opinion.

    Advisory throughout — a hard-to-follow piece ships anyway; this only tries to make it
    clearer first. Every repair is clarifying (handhold, cut, reorder, reader-side rewrite), so
    it adds no claims and no honesty gate re-runs after it.

    ``places`` are the country flags the page will carry. The reviewer may drop unearned ones
    outright or demand the clause that earns them; a drop alone does not trigger a repair lap,
    since removing the flag already resolves it.
    """
    review = build_comprehension_reviewer(context).invoke(
        {"draft": draft, "places": places or []}, config).get("comprehension_check") or {}

    # The flag decision belongs to the FIRST read — later reads are not shown the flags block —
    # so it is captured here and carried across every lap rather than being lost.
    drops = list(review.get("places_to_drop") or [])

    reviews = 1
    for lap in range(_MAX_REVIEW_LAPS):
        if not draft or str(review.get("verdict", "clear")) != "needs_ramp":
            break
        draft, profile, changed = _repair_once(
            context, config, draft=draft, treatment=treatment, profile=profile, review=review)
        if not changed:
            break            # the drafter produced nothing usable; another lap will not help
        if lap == _MAX_REVIEW_LAPS - 1:
            break            # final repair ships unreviewed — see the docstring
        review = build_comprehension_reviewer(context).invoke(
            {"draft": draft}, config).get("comprehension_check") or {}
        reviews += 1

    if drops:
        review = {**review, "places_to_drop": drops}
    return draft, profile, review, reviews


def _repair_once(
    context: AgentRunContext, config: RunnableConfig, *,
    draft: dict[str, Any], treatment: dict[str, Any], profile: dict[str, Any], review: dict[str, Any],
) -> tuple[dict[str, Any], dict[str, Any], bool]:
    """Send the review's findings back to the drafter once. Returns whether anything changed.

    Repair only — the caller decides whether the result is worth re-reading, because the last
    repair of a run deliberately is not. The reviewer's fixes are clarifying (handhold, cut,
    reorder, reader-side rewrite), so they add no claims and no honesty gate needs to re-run.

    If the drafter produces nothing usable, keep the original draft; the caller stops looping
    rather than burning another lap on the same failure.

    CRITICAL: a repair that *collapses* the body (handholds that wipe the article) is discarded.
    Live failure: ~400 words → ~21 words, then still published as a map + one sentence. This
    guard is mechanical and cheap, so it still protects the final unreviewed repair.
    """
    prior_words = _body_words(draft)
    repaired = build_drafter(context).invoke(
        {"treatment": treatment, "profile": profile, "prior_draft": draft,
         "comprehension_check": review}, config)
    new_draft = repaired.get("draft") or {}
    if not new_draft:
        return draft, profile, False
    new_words = _body_words(new_draft)
    collapsed = (
        prior_words >= _MIN_PUBLISH_WORDS
        and (new_words < _MIN_PUBLISH_WORDS
             or new_words < int(prior_words * _REPAIR_KEEP_FRAC))
    )
    if collapsed:
        context.emit(RAMP_REPAIRED, {
            "verdict": "repair_rejected_collapsed",
            "prior_words": prior_words, "new_words": new_words,
            "findings_remaining": len(review.get("findings", [])),
        })
        return draft, profile, False
    context.emit(RAMP_REPAIRED, {
        "verdict": "repaired",
        "findings_addressed": len(review.get("findings", [])),
        "prior_words": prior_words, "new_words": new_words,
    })
    return {**new_draft, "word_count": new_words}, repaired.get("profile") or profile, True


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
