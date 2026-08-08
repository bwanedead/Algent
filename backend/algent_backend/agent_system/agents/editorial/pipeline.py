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
import re
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
from .hero_stage import hero_enabled, is_quota_skip, make_hero
from .pipeline_contracts import EditorialPipelineReport
from .publish import render_published_article

PIPELINE_COMPLETED = "editorial_pipeline.completed"
PIPELINE_NO_INPUT = "editorial_pipeline.no_input"
CAVEAT_REPAIRED = "editorial_pipeline.caveat_repaired"   # the self-heal lap ran; here's the outcome
RAMP_REPAIRED = "editorial_pipeline.ramp_repaired"       # the comprehension repair lap ran
HERO_IMAGE = "editorial_pipeline.hero_image"             # hero generated / skipped, with the reason
SURFACE_REPAIRED = "editorial_pipeline.surface_repaired"  # cold-browser surface package re-ran

_STOPWORDS = frozenset({
    "a", "an", "the", "and", "or", "of", "in", "on", "to", "for", "with", "from",
    "into", "over", "under", "as", "by", "at", "is", "are", "was", "were", "be",
    "this", "that", "its", "their", "known", "called", "named",
})
_QUICK_TAKE_KEYS = ("what_happened", "why_it_matters", "what_is_uncertain")

# The analytics WORKER (grok subprocess) is gated separately from the router. The router is cheap
# (a nano assessment, always runs); the worker spends quota per request. ON by default so
# geography maps and trajectory charts actually ship — live runs with worker off planned
# figures that never appeared (Houthi choke-point, Wildberries strike map). Disable with
# ALGENT_ANALYTICS_WORKER=0. Cap still bounds cost.
_ANALYTICS_WORKER_ENV = "ALGENT_ANALYTICS_WORKER"
_ANALYTICS_CAP_ENV = "ALGENT_ANALYTICS_MAX"
# A COST BACKSTOP, NOT AN EDITORIAL TARGET. How many figures a story warrants is a judgement the
# router makes against the story; this number exists only because we cannot build infinitely many.
# It should almost never be the thing that decides.
#
# It was 2, and that was low enough to decide constantly. The Danube drought piece spent both
# slots on charts (generation mix, evening prices) and shipped no map of the river whose course
# through six countries was the mechanism of the whole story — not because anyone judged the map
# unhelpful, but because there was no slot left. A number that silently overrules the judgement it
# was meant to bound is set wrong. 7 is high enough that hitting it means something unusual about
# the story rather than something arbitrary about the limit.
#
# Zero is still success when nothing helps, and the router is told never to fill a quota — this
# ceiling is not a goal to reach.
_ANALYTICS_CAP_DEFAULT = 7

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
        treatment = _ensure_treatment(plan_out.get("treatment") or {}, profile)
        plan_report = plan_out.get("gauntlet") or {}

        # Visual PLAN early (cheap) so soft-cap repair spending cannot starve the plan.
        # Fulfillment runs after the final surface package.
        analytics_plan = _plan_analytics(context, config, profile, treatment)

        draft_out = build_drafting_gauntlet_graph(context).invoke(
            {"treatment": treatment, "profile": profile,
             "analytics_plan": analytics_plan}, config)
        draft = draft_out.get("draft") or {}
        enriched_profile = draft_out.get("profile") or profile
        draft_report = draft_out.get("gauntlet") or {}

        early = _hard_stop_without_draft(context, profile, treatment, draft)
        if early is not None:
            return early

        # Prose repairs first; final surface package (headline/quick_take/hero) runs AFTER
        # so title/gist match the repaired body.
        draft, enriched_profile, quality = _post_draft_quality(
            context, config, draft=draft, treatment=treatment, profile=enriched_profile)
        draft, hero, surface_issues = _headline_and_hero(
            context, config, draft, treatment=treatment)
        produced_analytics = _fulfill_analytics(
            context, config, analytics_plan, enriched_profile)
        # Data a figure went and sourced is evidence the profile did not have. Fold it into
        # the ledger rather than letting it die with the scratch folder — analytics is a
        # research act, and the numbers under a published chart should be as inspectable as
        # any other claim (and reusable in prose on a later lap).
        enriched_profile = _absorb_sourced_claims(
            context, enriched_profile, produced_analytics)
        quality = {
            **quality,
            "analytics": analytics_plan,
            "produced_analytics": produced_analytics,
            "surface_issues": surface_issues,
        }

        report = _build_pipeline_report(
            profile=profile, treatment=treatment, plan_report=plan_report,
            draft=draft, draft_report=draft_report, hero=hero, **quality,
        )
        _persist_pipeline_artifacts(
            context, draft=draft, profile=enriched_profile,
            analytics=produced_analytics, report=report,
        )
        context.emit(ev.OUTPUT_PREVIEW, _preview(report))
        context.emit(PIPELINE_COMPLETED, report.model_dump())
        return {"treatment": treatment, "draft": draft, "pipeline": report.model_dump()}

    graph = StateGraph(PipelineState)
    graph.add_node("pipeline", run)
    graph.add_edge(START, "pipeline")
    graph.add_edge("pipeline", END)
    return graph.compile()


def _hard_stop_without_draft(
    context: AgentRunContext,
    profile: dict[str, Any],
    treatment: dict[str, Any],
    draft: dict[str, Any],
) -> dict[str, Any] | None:
    if not (cost.is_hard_stop() and not draft.get("id")):
        return None
    report = EditorialPipelineReport(
        profile_id=str(profile.get("id", "")),
        status="hard_cost_cap",
        generated_at=datetime.now(UTC).isoformat(),
    )
    if context.artifacts is not None:
        context.artifacts.write_json("editorial_pipeline_report.json", report.model_dump())
    context.emit(PIPELINE_COMPLETED, report.model_dump())
    return {"treatment": treatment, "draft": draft, "pipeline": report.model_dump()}


def _plan_analytics(
    context: AgentRunContext, config: RunnableConfig,
    profile: dict[str, Any], treatment: dict[str, Any],
) -> dict[str, Any]:
    """Cheap visual plan — runs after treatment, before drafting; not slim-gated."""
    from algent_backend.agent_system.foundation.models.budget_gate import (
        BudgetRefusedError,
    )

    if cost.is_hard_stop():
        cost.record_skip("analytics_plan", "hard_stop")
        return {}
    try:
        return build_analytics_router(context).invoke(
            {"profile": profile, "treatment": treatment}, config,
        ).get("analytics_plan") or {}
    except BudgetRefusedError:
        cost.record_skip("analytics_plan", cost.mode())
        return {}


def _fulfill_analytics(
    context: AgentRunContext, config: RunnableConfig,
    analytics: dict[str, Any], profile: dict[str, Any],
) -> list[dict[str, Any]]:
    """Fulfill a prior visual plan — slim selection owned by budget_policy.

    Deferral policy (e.g. source_specimen → source_unavailable) is owned by the
    analytics router; this stage only fulfills still-requested items.
    """
    # Terminal plan statuses that must NOT be sent to the worker. Anything else
    # (including a model-hallucinated ``produced``) is treated as still open.
    _DEFERRED = frozenset({
        "not_warranted", "soft_cap_skipped", "worker_disabled", "source_unavailable",
    })
    reqs = list(analytics.get("requests") or [])
    if not reqs:
        return []

    active, deferred = [], []
    for r in reqs:
        status = str(r.get("status") or "requested").strip().lower() or "requested"
        if status in _DEFERRED:
            deferred.append({**r, "note": r.get("note") or r.get("rationale") or ""})
        else:
            # Reset fulfillment claims — only the worker may mark produced/failed.
            active.append({**r, "status": "requested"})

    if not analytics.get("warranted") or not active:
        return deferred
    if not _analytics_worker_enabled():
        return [{
            **r, "status": "worker_disabled", "note": "ALGENT_ANALYTICS_WORKER off",
        } for r in active] + deferred

    keep, skipped = budget_policy.select_analytics_requests(active, cap=_analytics_cap())
    if not keep:
        return skipped + deferred
    capped = {**analytics, "requests": keep}
    produced = build_analytics_worker_graph(context).invoke(
        {"analytics_plan": capped, "profile": profile}, config,
    ).get("analytics_artifacts") or []
    return produced + skipped + deferred


def _post_draft_quality(
    context: AgentRunContext, config: RunnableConfig, *,
    draft: dict[str, Any], treatment: dict[str, Any], profile: dict[str, Any],
) -> tuple[dict[str, Any], dict[str, Any], dict[str, Any]]:
    """Caveat + comprehension repairs after the first draft — before the final surface package."""
    from algent_backend.agent_system.foundation.models.budget_gate import (
        BudgetRefusedError,
    )

    caveat: dict[str, Any] = {}
    caveat_verdict = "verified"
    caveat_rounds = 0
    if budget_policy.allow_optional("caveat_check"):
        try:
            caveat = build_caveat_reviewer(context).invoke(
                {"draft": draft, "profile": profile}, config,
            ).get("caveat_check") or {}
            caveat_verdict = str(caveat.get("verdict", "verified"))
            caveat_rounds = 1
        except BudgetRefusedError:
            cost.record_skip("caveat_check", cost.mode())
    if caveat_verdict == "needs_hedging" and draft:
        if budget_policy.allow_optional("draft_repair"):
            draft, profile, caveat, caveat_rounds = _repair_hedging(
                context, config, draft=draft, treatment=treatment,
                profile=profile, caveat=caveat)
            caveat_verdict = str(caveat.get("verdict", "verified"))

    assigned_places = _derive_places(profile)
    if budget_policy.allow_optional("comprehension_repair"):
        draft, profile, comprehension, comprehension_rounds = _comprehension_pass(
            context, config, draft=draft, treatment=treatment, profile=profile,
            places=assigned_places)
    else:
        comprehension, comprehension_rounds = {}, 0

    return draft, profile, {
        "caveat_verdict": caveat_verdict,
        "caveat_rounds": caveat_rounds,
        "caveat_findings": len(caveat.get("findings", [])),
        "comprehension": comprehension,
        "comprehension_rounds": comprehension_rounds,
    }


def _build_pipeline_report(
    *,
    profile: dict[str, Any],
    treatment: dict[str, Any],
    plan_report: dict[str, Any],
    draft: dict[str, Any],
    draft_report: dict[str, Any],
    hero: dict[str, Any] | None,
    caveat_verdict: str,
    caveat_rounds: int,
    caveat_findings: int,
    comprehension: dict[str, Any],
    comprehension_rounds: int,
    analytics: dict[str, Any],
    produced_analytics: list[dict[str, Any]],
    surface_issues: list[str] | None = None,
) -> EditorialPipelineReport:
    outcome = str(draft_report.get("outcome", ""))
    words = _body_words(draft)
    if draft:
        draft["word_count"] = words
    status = _pipeline_status(outcome, caveat_verdict, words, profile)
    if cost.is_hard_stop() and draft.get("id"):
        status = "cost_capped"
    issues = list(surface_issues or [])
    # Hero required except Gemini quota (soft-skip) or ALGENT_HERO_IMAGE=0.
    if hero_enabled() and not (isinstance(hero, dict) and hero.get("artifact_name")):
        if is_quota_skip(hero):
            if "hero_quota_skipped" not in issues:
                issues.append("hero_quota_skipped")
        else:
            status = "needs_hero"
            if "hero_missing" not in issues:
                issues.append("hero_missing")
    skipped = [
        f"{a.get('request_id') or a.get('id') or '?'}:{a.get('status')}"
        for a in produced_analytics
        if a.get("status") and a.get("status") != "produced"
    ]
    return EditorialPipelineReport(
        profile_id=str(profile.get("id", "")),
        treatment_id=str(treatment.get("id", "")),
        treatment_verdict=str(plan_report.get("final_verdict", "")),
        draft_id=str(draft.get("id", "")),
        draft_outcome=outcome,
        publishable=status == "publishable",
        status=status,
        caveat_verdict=caveat_verdict,
        caveat_findings=caveat_findings,
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
        analytics_produced=sum(
            1 for a in produced_analytics
            if a.get("status") == "produced" and (a.get("artifact_name") or a.get("body_md"))
        ),
        analytics_escapes=sum(1 for a in produced_analytics if a.get("escaped_writes")),
        analytics_skipped=skipped,
        analytics_failures=_analytics_failures(produced_analytics),
        surface_issues=issues,
        generated_at=datetime.now(UTC).isoformat(),
    )


def _persist_pipeline_artifacts(
    context: AgentRunContext, *,
    draft: dict[str, Any], profile: dict[str, Any],
    analytics: list[dict[str, Any]], report: EditorialPipelineReport,
) -> None:
    if context.artifacts is None or not draft:
        return
    draft_obj = ArticleDraft.model_validate(draft)
    context.artifacts.write_text(
        "article_published.md",
        render_published_article(
            draft_obj, SignalProfile.model_validate(profile), analytics))
    context.artifacts.write_text("article.md", render_draft(draft_obj))
    context.artifacts.write_json("editorial_pipeline_report.json", report.model_dump())


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
    *, treatment: dict[str, Any] | None = None,
) -> tuple[dict[str, Any], dict[str, Any] | None, list[str]]:
    """Final surface package after prose repairs — title, dek, quick_take, hero.

    Runs one bounded cold-browser repair when mechanical checks fail, then soft-ships
    any remaining issues on the report.
    """
    hero: dict[str, Any] | None = None
    issues: list[str] = []
    if not draft:
        return draft, hero, issues
    with cost.essential_scope():
        invoke_in: dict[str, Any] = {"draft": draft}
        if treatment:
            invoke_in["treatment"] = treatment
        hl = build_headline_writer(context).invoke(invoke_in, config).get("headline") or {}
        draft = _apply_headline(draft, hl, treatment=treatment)
        issues = _surface_cold_browser_issues(draft, treatment)
        if issues:
            repair_in = {**invoke_in, "draft": draft, "surface_issues": issues}
            repaired = build_headline_writer(context).invoke(repair_in, config).get("headline") or {}
            # Keep image fields from the first pass when the repair omits them — hero runs once.
            for key in ("image_subject", "image_hook"):
                if not str(repaired.get(key) or "").strip() and str(hl.get(key) or "").strip():
                    repaired[key] = hl[key]
            hl = repaired or hl
            draft = _apply_headline(draft, hl, treatment=treatment)
            remaining = _surface_cold_browser_issues(draft, treatment)
            context.emit(SURFACE_REPAIRED, {
                "prior_issues": issues, "remaining_issues": remaining,
            })
            issues = remaining
        hero = make_hero(hl, context.artifacts, say=lambda m: context.emit(HERO_IMAGE, {"note": m}))
    return draft, hero, issues


def _apply_headline(
    draft: dict[str, Any], hl: dict[str, Any], *, treatment: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Apply headline fields; merge quick_take field-by-field so partial outputs keep fallbacks."""
    if not hl:
        return draft
    out = {**draft}
    if hl.get("title"):
        out["title"] = hl["title"]
        out["standfirst"] = hl.get("standfirst") or draft.get("standfirst", "")

    prior = draft.get("quick_take") if isinstance(draft.get("quick_take"), dict) else {}
    # Treatment entry is the durable fallback when headline/drafter leave a field blank.
    fallback = {
        "what_happened": str((treatment or {}).get("news_kernel") or ""),
        "why_it_matters": str((treatment or {}).get("reader_payoff") or ""),
        "what_is_uncertain": str((treatment or {}).get("key_uncertainty") or ""),
    }
    incoming = hl.get("quick_take") if isinstance(hl.get("quick_take"), dict) else {}
    merged: dict[str, str] = {}
    for key in _QUICK_TAKE_KEYS:
        for candidate in (incoming.get(key), prior.get(key), fallback.get(key)):
            text = str(candidate or "").strip()
            if text:
                merged[key] = text
                break
        else:
            merged[key] = ""
    if any(merged.values()):
        out["quick_take"] = merged
    return out


def _surface_cold_browser_issues(
    draft: dict[str, Any], treatment: dict[str, Any] | None,
) -> list[str]:
    """Mechanical cold-browser checks on the final surface — advisory, one repair lap max."""
    issues: list[str] = []
    title = str(draft.get("title") or "").strip()
    standfirst = str(draft.get("standfirst") or "").strip()
    surface = f"{title} {standfirst}".casefold()
    qt = draft.get("quick_take") if isinstance(draft.get("quick_take"), dict) else {}
    plain = str((treatment or {}).get("plain_subject") or "").strip()
    kernel = str((treatment or {}).get("news_kernel") or "").strip()
    payoff = str((treatment or {}).get("reader_payoff") or "").strip()
    uncertainty = str((treatment or {}).get("key_uncertainty") or "").strip()

    if plain:
        words = [
            w for w in re.findall(r"[a-z0-9]+", plain.casefold())
            if len(w) > 3 and w not in _STOPWORDS
        ]
        if words and not any(w in surface for w in words):
            issues.append(
                f"title/dek omit plain_subject ({plain!r}); a specialist name alone fails "
                "a cold browser"
            )

    if re.fullmatch(r"[A-Z]{2,8}", title):
        issues.append(f"title is only an initialism ({title!r})")

    expected = (
        ("what_happened", kernel),
        ("why_it_matters", payoff),
        ("what_is_uncertain", uncertainty),
    )
    for field, source in expected:
        if source and not str(qt.get(field) or "").strip():
            issues.append(f"quick_take.{field} is empty")
    return issues


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
    draft: dict[str, Any], treatment: dict[str, Any],
    profile: dict[str, Any], caveat: dict[str, Any],
) -> tuple[dict[str, Any], dict[str, Any], dict[str, Any], int]:
    """One bounded lap that repairs an overclaim instead of parking the piece.

    Headline/quick_take are NOT refreshed here — the final surface package runs after all
    prose repairs so the title stays truthful to the last body.
    """
    repaired = build_drafter(context).invoke(
        {
            "treatment": treatment,
            "profile": profile,
            "prior_draft": draft,
            "caveat_check": caveat,
        },
        config,
    )
    new_draft = repaired.get("draft") or {}
    if not new_draft:
        return draft, profile, caveat, 2

    profile = repaired.get("profile") or profile
    rechecked = build_caveat_reviewer(context).invoke(
        {"draft": new_draft, "profile": profile}, config).get("caveat_check") or {}
    context.emit(CAVEAT_REPAIRED, {"verdict": rechecked.get("verdict"),
                                   "findings_remaining": len(rechecked.get("findings", []))})
    return new_draft, profile, rechecked, 2


ANALYTICS_CLAIMS_ADDED = "editorial_pipeline.analytics_claims_added"


def _absorb_sourced_claims(
    context: AgentRunContext,
    profile: dict[str, Any],
    artifacts: list[dict[str, Any]],
) -> dict[str, Any]:
    """Add a sourced figure's data to the claim ledger, with its publisher as a source.

    Marked ``sourced_by: analytics`` and graded ``likely`` rather than confirmed: this came
    from a figure's own fetch, not from the research pass that reads and grades sources, and
    the ledger should not pretend otherwise. It is real, attributed evidence — it just has a
    different provenance from a deep-read claim, and saying so is the whole point of a ledger.
    """
    rows = [row for a in artifacts or [] for row in (a.get("sourced_claims") or [])]
    if not rows:
        return profile

    import hashlib

    out = dict(profile)
    claims = list(out.get("claim_ledger") or [])
    sources = list(out.get("source_ledger") or [])
    by_url = {str(s.get("url") or ""): s for s in sources}
    existing = {str(c.get("text") or "") for c in claims}
    added = 0

    for row in rows:
        text, url = str(row.get("text") or "").strip(), str(row.get("url") or "").strip()
        if not text or not url or text in existing:
            continue
        src = by_url.get(url)
        if src is None:
            sid = "src_an_" + hashlib.sha1(url.encode("utf-8")).hexdigest()[:10]
            src = {"id": sid, "url": url, "source_type": "secondary",
                   "title": "sourced for a figure"}
            sources.append(src)
            by_url[url] = src
        claims.append({
            "id": "clm_an_" + hashlib.sha1(text.encode("utf-8")).hexdigest()[:10],
            "text": text,
            "grade": "likely",
            "salience": "low",
            "supported_by": [src["id"]],
            "sourced_by": "analytics",
        })
        existing.add(text)
        added += 1

    if not added:
        return profile
    out["claim_ledger"] = claims
    out["source_ledger"] = sources
    context.emit(ANALYTICS_CLAIMS_ADDED, {"claims_added": added})
    return out


def _analytics_failures(artifacts: list[dict[str, Any]]) -> list[str]:
    """One readable line per figure that did not ship, with the reason attached.

    Also catches the *silent* failure: an artifact that claims ``produced`` while carrying no
    file and no body. That one shipped a rail reporting ``analytics_produced=1`` against an
    empty assets directory, which is the worst shape a failure can take — it looks like
    success everywhere except on the page.
    """
    out: list[str] = []
    for art in artifacts or []:
        status = str(art.get("status") or "")
        has_output = bool(art.get("artifact_name") or art.get("body_md"))
        if status == "produced" and has_output:
            continue
        rid = str(art.get("request_id") or "?")
        note = str(art.get("note") or "").strip()
        if status == "produced" and not has_output:
            status, note = "produced_but_empty", note or "claimed produced with no artifact on disk"
        out.append(f"{rid}: {status}" + (f" — {note[:160]}" if note else ""))
    return out


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
    draft: dict[str, Any], treatment: dict[str, Any],
    profile: dict[str, Any], review: dict[str, Any],
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
    summary = (
        f"{r.word_count} words | status: {r.status} | draft: {r.draft_outcome} | "
        f"caveats: {r.caveat_verdict}"
        + (f" ({r.caveat_findings} to fix)" if r.caveat_findings else "")
        + (f" | walls: {r.barriers}" if r.barriers else "")
    )
    if r.analytics_skipped:
        summary += f" | visuals skipped: {len(r.analytics_skipped)}"
    # Figures are the thing most often silently absent, so say it in the one line an operator
    # reads: "1/2 figures" beats discovering an empty assets folder on the published page.
    if r.analytics_warranted:
        summary += f" | figures: {r.analytics_produced}/{r.analytics_count}"
    if r.surface_issues:
        summary += f" | surface issues: {len(r.surface_issues)}"
    items = [f"treatment: {r.treatment_id}", f"draft: {r.draft_id}"]
    items += [f"figure failed — {reason}" for reason in r.analytics_failures[:4]]
    return {
        "title": f"article: {r.article_title[:70] or '(untitled)'}",
        "summary": summary,
        "items": items,
        "link": "../artifacts/article.md",
    }
