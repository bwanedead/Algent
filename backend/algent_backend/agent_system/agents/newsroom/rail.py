"""
The full newsroom rail (v1) — raw discovery pool -> finished, receipted article, one run.

    [backfeed intake] -> synthesis -> routing -> profile -> profile gauntlet -> editorial pipeline

Or, when a prior t1 portfolio is supplied (``--from-run`` / state.portfolio):

    [reuse portfolio] -> routing (cooldown) -> profile -> gauntlet -> editorial

It chains the stages that already work as sub-graphs under ONE run/context (the same idiom the
gauntlets and the editorial pipeline use), so every stage's events land in this run's timeline and
a single report closes the loop. Four deliberate properties:

  (i)   COST — the rail wraps the run in ``cost.article_scoped`` and buckets
        ``article_spent_usd`` by ``RAIL_STAGE``, so every finished article carries
        what it actually cost to make (stage allowances draw from one remaining pool).
  (ii)  BOUNDED — the rail inherits each stage's own floors (models, paid budgets, USD caps, review
        gates); it re-litigates none of them. It promotes the router's single #1 vector — one article
        per run — rather than fanning out.
  (iii) BACKFEED — **OFF by default.** Opt-in only (``ALGENT_BACKFEED=1``). When on, open research
        leads re-enter the t0 pool. Live regression 0022: ICE open leads re-seeded the same
        published family and beat cooldown. Default stays off until backfeed is gated by cooldown.
  (iv)  REUSE — a post-t0 launch can skip discovery and re-route a prior portfolio. The same
        headline-ring cooldown applies as on a fresh run (cooled story-families cannot promote
        until they fall off the ring). Saves t0/synthesis cost only — not a variety bypass.

Each stage can legitimately be the end: no promotable vector is a valid outcome, not an error.
Profile readiness is diagnosed honestly (disposition on the report) but does not hard-stop the
rail — the site is the review surface, so immature profiles still draft and publish with their
quality status visible for the feedback loop.
"""

from __future__ import annotations

import dataclasses
import os
import sys
import time
from datetime import UTC, datetime
from typing import Any, TypedDict

from langchain_core.runnables import RunnableConfig
from langgraph.graph import END, START, StateGraph

from algent_backend.agent_system.agents.research.leads import (
    JsonLeadStore,
    open_leads_for_discovery,
)
from algent_backend.agent_system.foundation import cost
from algent_backend.agent_system.runs import events as ev
from algent_backend.agent_system.runs.context import AgentRunContext
from algent_backend.agent_system.runs.control_plane.layout import find_run_root
from algent_backend.publishing import publish as pb
from algent_backend.publishing import site_git
from algent_backend.publishing.x_article import announce as announce_article

from ..discovery.synthesis.spec import build_graph as build_synthesis
from ..editorial.pipeline_spec import build_graph as build_editorial
from ..gauntlet.spec import build_graph as build_profile_gauntlet
from ..research.spec import build_graph as build_profile
from ..routing.spec import build_graph as build_router
from .rail_contracts import NewsroomRailReport

RAIL_COMPLETED = "newsroom_rail.completed"
RAIL_STAGE = "newsroom_rail.stage"
RAIL_ANNOUNCED = "newsroom_rail.announced"
BACKFEED_INJECTED = "newsroom_rail.backfeed_injected"
RAIL_PUBLISHED = "newsroom_rail.published"

# Backfeed is OFF by default. It was meant to re-queue unfinished research threads, but live
# it re-injected the same published story-family (ICE 0020→0022) and fought cooldown. Opt in
# only with ALGENT_BACKFEED=1 after it is gated against recent headlines. Cap still applies.
_BACKFEED_ENV = "ALGENT_BACKFEED"
_BACKFEED_CAP_ENV = "ALGENT_BACKFEED_MAX"
_BACKFEED_CAP_DEFAULT = 5

# Where a backfed lead sits relative to fresh t0 signal: present and competing, but never
# dominating a genuinely hot story (top t0 scores run ~7+). Confidence sets the rung.
_LEAD_SCORE = {"high": 5.0, "med": 3.0, "medium": 3.0, "low": 1.5, "": 2.0}


def _backfeed_enabled() -> bool:
    # Default OFF — must opt in. (Was default ON; caused same-story repetition.)
    return os.environ.get(_BACKFEED_ENV, "0").strip().lower() in ("1", "true", "yes", "on")


def _backfeed_cap() -> int:
    try:
        return max(0, int(os.environ.get(_BACKFEED_CAP_ENV, _BACKFEED_CAP_DEFAULT)))
    except ValueError:
        return _BACKFEED_CAP_DEFAULT


class RailState(TypedDict, total=False):
    pool: dict[str, Any]            # optional t0 pool; synthesis self-sources if absent
    portfolio: dict[str, Any]       # optional t1 portfolio — when set, skip t0+synthesis (reuse)
    source_run_id: str              # prior run id when portfolio was reused (observability)
    rail: dict[str, Any]            # the NewsroomRailReport
    pipeline: dict[str, Any]        # the editorial pipeline's report (the article)


def build_newsroom_rail_graph(context: AgentRunContext, *, lead_store: Any | None = None) -> Any:
    """Compile the full-rail orchestrator. ``lead_store`` is injectable (tests pass a fake)."""

    def run(state: RailState, config: RunnableConfig) -> dict[str, Any]:
        with cost.article_scoped():
            return _run_rail(context, state, config, lead_store=lead_store)

    graph = StateGraph(RailState)
    graph.add_node("run", run)
    graph.add_edge(START, "run")
    graph.add_edge("run", END)
    return graph.compile()


def _run_rail(
    context: AgentRunContext, state: RailState, config: RunnableConfig, *, lead_store: Any | None,
) -> dict[str, Any]:
    sub, x_calls, clock = _install_cost_tee(context)
    # Module-level so every _finish path picks up timings without threading the clock through
    # six signatures. Safe because the single-flight lock guarantees one rail per process.
    global _CLOCK
    _CLOCK = clock
    report = NewsroomRailReport(generated_at=datetime.now(UTC).isoformat())

    pool, portfolio, early = _resolve_portfolio(
        context, sub, state, config, report, lead_store=lead_store)
    if early is not None:
        return _finish_with_cost(context, report, early)

    profile, early = _route_profile_gauntlet(
        context, sub, config, report, pool=pool, portfolio=portfolio)
    if early is not None:
        return _finish_with_cost(context, report, early)

    return _editorial_and_publish(
        context, sub, config, report, profile, x_calls=x_calls,
    )


def _install_cost_tee(context: AgentRunContext) -> tuple[Any, list[int], StageClock]:
    """Forward events; label the article ledger from RAIL_STAGE. Returns (sub_ctx, x_calls, clock).

    Also the natural place to TIME the rail, because it already sees every stage transition.
    """
    x_calls = [0]
    clock = StageClock()

    def _tee(event_type: str, payload: dict[str, Any] | None = None) -> None:
        p = payload or {}
        if event_type == RAIL_STAGE and p.get("stage"):
            cost.set_stage(str(p["stage"]))
            clock.enter(str(p["stage"]))
        if event_type in _SLOW_LEG_EVENTS:
            clock.mark(event_type, p)
        if event_type == ev.TOOL_RESULT and '"kind": "x"' in str(p.get("content", "")):
            x_calls[0] += 1
        context.emit(event_type, p)

    return dataclasses.replace(context, emit=_tee), x_calls, clock


#: Events worth timing INSIDE a stage. "editorial" is one rail stage but many minutes, and the
#: minutes are not evenly spread — a figure that times out spends ten of them in a subprocess
#: whose calls never appear on the model dashboard, which reads from outside as a dead run.
_SLOW_LEG_EVENTS = frozenset({
    "analytics_worker.ready",
    "analytics_worker.artifact",
    "editorial_pipeline.hero_image",
    "editorial_pipeline.analytics_claims_confirmed",
    "draft.completed",
    "comprehension_check.completed",
    "headline.completed",
})


#: Set per run in _run_rail; read by every _finish path. See the note there.
_CLOCK: StageClock | None = None


class StageClock:
    """Wall time per rail stage, printed as it happens and kept for the report.

    Cost was already attributed by stage; TIME was not, so "why has this been running for
    twenty minutes" could only be answered by reading raw event timestamps out of a run's
    timeline after the fact. This makes it answerable while the run is still going.
    """

    def __init__(self) -> None:
        self.stages: list[dict[str, Any]] = []
        self.legs: list[dict[str, Any]] = []
        self._t0 = time.monotonic()

    def enter(self, stage: str) -> None:
        now = time.monotonic()
        if self.stages:
            prev = self.stages[-1]
            prev["seconds"] = round(now - prev["_start"], 1)
            self._say(f"[stage] {prev['stage']} finished in {_hms(prev['seconds'])}")
        self.stages.append({"stage": stage, "_start": now, "seconds": None})
        self._say(f"[stage] {stage} started (+{_hms(now - self._t0)} into the run)")

    def mark(self, event_type: str, payload: dict[str, Any]) -> None:
        """Note a slow leg inside the current stage, so a long stage is not opaque."""
        now = time.monotonic()
        last = self.legs[-1]["_at"] if self.legs else (
            self.stages[-1]["_start"] if self.stages else self._t0)
        label = event_type.split(".")[-1]
        detail = str(payload.get("request_id") or payload.get("note") or "")[:80]
        self.legs.append({"event": event_type, "detail": detail,
                          "since_previous_s": round(now - last, 1), "_at": now})
        self._say(f"[leg]   {label} (+{_hms(now - last)}){f' — {detail}' if detail else ''}")

    def close(self) -> None:
        if self.stages and self.stages[-1]["seconds"] is None:
            last = self.stages[-1]
            last["seconds"] = round(time.monotonic() - last["_start"], 1)
            self._say(f"[stage] {last['stage']} finished in {_hms(last['seconds'])}")

    def summary(self) -> dict[str, Any]:
        self.close()
        return {
            "total_seconds": round(time.monotonic() - self._t0, 1),
            "by_stage": {s["stage"]: s["seconds"] for s in self.stages},
            "slow_legs": [
                {k: v for k, v in leg.items() if not k.startswith("_")}
                for leg in sorted(self.legs, key=lambda x: -x["since_previous_s"])[:12]
            ],
        }

    @staticmethod
    def _say(line: str) -> None:
        print(line, file=sys.stderr, flush=True)


def _hms(seconds: float) -> str:
    seconds = max(0.0, float(seconds))
    if seconds < 60:
        return f"{seconds:.0f}s"
    return f"{int(seconds // 60)}m{int(seconds % 60):02d}s"


def _apply_cost_snapshot(report: NewsroomRailReport) -> None:
    snap = cost.snapshot()
    report.total_usd = float(snap.get("spent_usd") or 0.0)
    report.soft_cap_usd = float(snap.get("soft_cap_usd") or cost.soft_cap_usd())
    report.hard_cap_usd = float(snap.get("hard_cap_usd") or cost.hard_cap_usd())
    report.budget_mode = str(snap.get("mode") or "normal")
    report.soft_cap_crossed = bool(snap.get("soft_cap_crossed"))
    report.soft_crossed_at_stage = str(snap.get("soft_crossed_at_stage") or "")
    report.hard_stop = bool(snap.get("hard_stop"))
    report.hard_stop_stage = str(snap.get("hard_stop_stage") or "")
    report.cost_by_stage = dict(snap.get("cost_by_stage") or {})
    report.cost_by_op = dict(snap.get("cost_by_op") or {})
    report.skipped_operations = list(snap.get("skipped_operations") or [])
    report.refused_operations = list(snap.get("refused_operations") or [])


def _finish_with_cost(
    context: AgentRunContext, report: NewsroomRailReport, early: dict[str, Any],
) -> dict[str, Any]:
    """Re-finish an early exit after snapshotting the article ledger onto the report."""
    _apply_cost_snapshot(report)
    return _finish(
        context, report,
        pipeline=early.get("pipeline") or {},
        total=report.total_usd,
    )


def _resolve_portfolio(
    context: AgentRunContext, sub: AgentRunContext, state: RailState, config: RunnableConfig,
    report: NewsroomRailReport, *, lead_store: Any | None,
) -> tuple[dict | None, dict[str, Any], dict[str, Any] | None]:
    """Discovery synthesis or portfolio reuse. Returns (pool, portfolio, early_finish_or_None)."""
    pool = state.get("pool")
    reused = state.get("portfolio") or {}
    if reused.get("vectors"):
        portfolio = reused
        report.portfolio_source = "reused"
        report.source_run_id = str(state.get("source_run_id") or "")
        report.vector_count = len(portfolio.get("vectors", []))
        report.pool_items = int(portfolio.get("total_considered", 0) or 0)
        report.stage_reached = "synthesis"
        sub.emit(RAIL_STAGE, {
            "stage": "synthesis", "skipped": True, "reason": "portfolio_reused",
            "source_run_id": report.source_run_id, "vector_count": report.vector_count,
        })
        return pool, portfolio, None

    if _backfeed_enabled():
        pool, injected = _inject_backfeed(context, pool, lead_store or JsonLeadStore())
        report.backfeed_leads_injected = injected

    # Durable operator pause (flags.SYNTHESIS_ENABLED): when off the rail needs an
    # explicit portfolio (compose / pick / --from-run), not a fresh t1 build.
    from .flags import synthesis_enabled
    if not synthesis_enabled():
        report.portfolio_source = "paused"
        report.stage_reached = "synthesis"
        sub.emit(RAIL_STAGE, {
            "stage": "synthesis", "skipped": True, "reason": "synthesis_disabled",
        })
        return pool, {}, _finish(
            context, report,
            note="synthesis off (flags.SYNTHESIS_ENABLED) — compose/pick a t0 lead or set True",
        )

    sub.emit(RAIL_STAGE, {"stage": "synthesis"})
    syn_input: dict[str, Any] = {"pool": pool} if pool is not None else {}
    portfolio = build_synthesis(sub).invoke(syn_input, config).get("portfolio") or {}
    report.portfolio_source = "fresh"
    report.vector_count = len(portfolio.get("vectors", []))
    report.pool_items = int(portfolio.get("total_considered", 0) or 0)
    report.stage_reached = "synthesis"
    if not portfolio.get("vectors"):
        return pool, portfolio, _finish(context, report, note="synthesis produced no vectors")
    return pool, portfolio, None


def _route_profile_gauntlet(
    context: AgentRunContext, sub: AgentRunContext, config: RunnableConfig,
    report: NewsroomRailReport, *, pool: dict | None, portfolio: dict[str, Any],
) -> tuple[dict[str, Any], dict[str, Any] | None]:
    """Routing → profile → gauntlet. Returns (profile, early_finish_or_None)."""
    sub.emit(RAIL_STAGE, {"stage": "routing"})
    route = build_router(sub).invoke({"portfolio": portfolio}, config)
    vector = route.get("selected_vector")
    report.stage_reached = "routing"
    if not vector:
        return {}, _finish(context, report, note="routing promoted no vector")
    report.selected_vector_id = str(vector.get("id", ""))
    report.selected_vector_title = str(vector.get("title", ""))
    report.pool_by_channel, report.promoted_from = _channel_provenance(context, pool, vector)

    sub.emit(RAIL_STAGE, {"stage": "profile"})
    profile = build_profile(sub).invoke(
        {"vector": vector, "pool": pool}, config,
    ).get("profile") or {}
    report.stage_reached = "profile"
    if not profile.get("id"):
        return profile, _finish(context, report, note="profile research produced nothing")
    report.profile_id = str(profile.get("id", ""))

    sub.emit(RAIL_STAGE, {"stage": "gauntlet"})
    g = build_profile_gauntlet(sub).invoke({"profile": profile}, config)
    profile = g.get("profile") or profile
    gauntlet = g.get("gauntlet") or {}
    report.gauntlet_verdict = str(gauntlet.get("final_verdict", ""))
    report.stage_reached = "gauntlet"
    _record_profile_disposition(report, profile, gauntlet)
    return profile, None


def _record_profile_disposition(
    report: NewsroomRailReport, profile: dict[str, Any], gauntlet: dict[str, Any],
) -> None:
    """Soft readiness diagnose — disposition on the report, never a hard stop."""
    _ready, disposition, why = _profile_ready_for_prose(profile, gauntlet)
    if disposition:
        report.disposition = disposition
        report.note = why


def _editorial_and_publish(
    context: AgentRunContext, sub: AgentRunContext, config: RunnableConfig,
    report: NewsroomRailReport, profile: dict[str, Any], *,
    x_calls: list[int],
) -> dict[str, Any]:
    """Draft → publish. Fail-open publish; quality status rides on the report."""
    sub.emit(RAIL_STAGE, {"stage": "editorial"})
    pipeline = build_editorial(sub).invoke({"profile": profile}, config).get("pipeline") or {}
    report.article_status = str(pipeline.get("status", ""))
    report.article_title = str(pipeline.get("article_title", ""))
    report.analytics_produced = int(pipeline.get("analytics_produced", 0) or 0)
    report.stage_reached = "complete"
    _apply_cost_snapshot(report)
    report.x_searches = x_calls[0]
    # Write the report BEFORE publish so the digest sees disposition, provenance, and cost.
    if context.artifacts is not None:
        context.artifacts.write_json("newsroom_rail_report.json", report.model_dump())
    sub.emit(RAIL_STAGE, {"stage": "publish"})
    _publish(context, report)
    return _finish(context, report, pipeline=pipeline, total=report.total_usd)


def _channel_provenance(
    context: AgentRunContext, pool: dict | None, vector: dict,
) -> tuple[dict[str, int], dict[str, int]]:
    """(what each channel contributed, which channels fed the PROMOTED story).

    Derived, not instrumented: a vector already cites its ``supporting_hits`` (t0 item ids) and each
    pool item already carries its ``channel``, so provenance is a join — no synthesis change needed.

    The pair is the point. Pool share alone says nothing; the ratio of "share of the pool" to "share
    of what actually got promoted" is the overfit signal. A live run made this concrete: X supplied
    a quarter of the pool and 100% of the promoted story, while a constitutional crisis sourced from
    GDELT lost — a steer that is invisible without measuring both sides.
    """
    if pool is None:                       # synthesis self-sourced it; read this run's snapshot
        try:
            run_dir = find_run_root(context.run_id)
            if run_dir is None:
                return {}, {}
            import json as _json
            pool = _json.loads((run_dir / "artifacts" / "t0_pool.json").read_text(encoding="utf-8"))
        except Exception:  # noqa: BLE001 — observability must never break a run
            return {}, {}

    items = pool.get("items") or []
    by_id = {str(i.get("id")): str(i.get("channel") or "?") for i in items}
    pool_counts: dict[str, int] = {}
    for ch in by_id.values():
        pool_counts[ch] = pool_counts.get(ch, 0) + 1

    promoted: dict[str, int] = {}
    for hit in (vector.get("supporting_hits") or []):
        ch = by_id.get(str(hit))
        if ch:
            promoted[ch] = promoted.get(ch, 0) + 1
    return pool_counts, promoted


def _publish(context: AgentRunContext, report: NewsroomRailReport) -> None:
    """Ship the finished piece. The rail publishes ITSELF — that is the whole design.

    The floors already made the call (only a caveat-verified `publishable` piece is eligible; the
    self-heal lap already repaired what it could), so there is no human decision left to wait for.
    Publishing as a manual command afterwards was the friction this removes.

    The run's artifacts must already be on disk — they are: every stage wrote through this run's
    artifact store, and the rail report is written just below with the publish outcome folded in.
    Best-effort by construction: a distribution failure must never retroactively fail an article
    that the newsroom already produced honestly, so anything here is caught and recorded.
    """
    try:
        run_dir = find_run_root(context.run_id)
        if run_dir is None:
            report.publish_action = "skipped (run dir not found)"
            return
        root = site_git.repo_root(run_dir)
        push = site_git.publish_enabled()
        worktree = None
        if push:
            worktree, note = site_git.ensure_worktree(root)
            if worktree is None:
                report.publish_action = f"skipped ({note[:80]})"
                return
        target = site_git.live_site_dir(root) if push else site_git.site_dir(root)

        result = pb.publish_run(run_dir, site_dir=target, held_dir=root / "backend" / "publish_held",
                                push=push)
        report.publish_action = result.action
        report.published_slug = result.slug
        if push and worktree is not None and result.action in ("published", "corrected"):
            ok, _note = site_git.commit_and_push(
                worktree, message=f"publish({result.slug}): {result.status}\n\n{result.digest}")
            report.published = ok
            if not ok:
                report.publish_action = "push_failed"
        context.emit(RAIL_PUBLISHED, {"action": report.publish_action, "slug": report.published_slug,
                                      "published": report.published, "reasons": result.reasons})
        # Live on the site and unmentioned on the timeline is a half-published article. Announcing
        # is part of publishing, not a thing to remember afterwards.
        if report.published:
            announced = announce_article(report.published_slug, report.article_title)
            context.emit(RAIL_ANNOUNCED, announced)
    except Exception as exc:  # noqa: BLE001 — see docstring: distribution never fails the article
        report.publish_action = f"error ({str(exc)[:90]})"
        context.emit(RAIL_PUBLISHED, {"action": report.publish_action, "published": False})


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


# Profile gauntlet verdicts that are ready without a soft-warning disposition.
# Soft enrichment leftovers are fine; verification/unsound get a disposition note but
# still proceed — the site is the review surface.
_PROSE_READY_VERDICTS = frozenset({"mature", "needs_enrichment"})
_BLOCKING_PROFILE_STATUSES = frozenset({
    "needs_verification", "insufficient_evidence", "unsound",
})


def _profile_ready_for_prose(
    profile: dict[str, Any], gauntlet: dict[str, Any],
) -> tuple[bool, str, str]:
    """Return (ready, disposition, note). Soft diagnose only — never hard-stops the rail.

    Review already diagnosed maturity; we surface that as disposition so the published
    artifact carries why it was weak. Editorial still runs: publishing is the feedback loop.
    """
    verdict = str(gauntlet.get("final_verdict") or "").strip()
    status = str(profile.get("profile_status") or "").strip()

    if verdict in ("needs_verification", "unsound") or not verdict:
        disposition = verdict or "held"
        return False, disposition, f"profile soft-warn (gauntlet: {disposition})"
    if status in _BLOCKING_PROFILE_STATUSES:
        return False, status, f"profile soft-warn (status: {status})"
    if verdict not in _PROSE_READY_VERDICTS:
        return False, "held", f"profile soft-warn (gauntlet: {verdict})"
    return True, "", ""


def _finish(
    context: AgentRunContext, report: NewsroomRailReport, *,
    pipeline: dict | None = None, total: float = 0.0, note: str = "",
) -> dict[str, Any]:
    if note:
        report.note = note
    report.total_usd = total
    if _CLOCK is not None:
        timings = _CLOCK.summary()
        report.total_seconds = float(timings["total_seconds"])
        report.stage_seconds = {k: v for k, v in timings["by_stage"].items() if v is not None}
        report.slow_legs = timings["slow_legs"]
        if context.artifacts is not None:
            context.artifacts.write_json("stage_timings.json", timings)
    if context.artifacts is not None:
        context.artifacts.write_json("newsroom_rail_report.json", report.model_dump())
    context.emit(ev.OUTPUT_PREVIEW, _preview(report))
    context.emit(RAIL_COMPLETED, report.model_dump())
    return {"rail": report.model_dump(), "pipeline": pipeline or {}}


def _preview(r: NewsroomRailReport) -> dict[str, Any]:
    if r.portfolio_source == "reused":
        origin = f"reused portfolio ({r.vector_count} vectors"
        if r.source_run_id:
            origin += f" from {r.source_run_id[:8]}"
        origin += ")"
    else:
        origin = (
            f"{r.pool_items} t0 items (+{r.backfeed_leads_injected} backfed) "
            f"-> {r.vector_count} vectors"
        )
    return {
        "title": f"full rail -> {r.stage_reached}",
        "summary": (
            origin
            + (f" -> promoted: {r.selected_vector_title[:50]}" if r.selected_vector_title else "")
            + (f" -> held: {r.disposition}" if r.disposition else "")
            + (f" -> article: {r.article_status}" if r.article_status else "")
            + (f" -> {r.publish_action}" if r.publish_action else "")
            + f"  ·  ~${r.total_usd:.4f}"
            + (f"  ·  {_hms(r.total_seconds)}" if r.total_seconds else "")
            + (f"  ·  {r.note}" if r.note else "")
        ),
        "items": [
            f"profile: {r.profile_id or '—'} ({r.gauntlet_verdict or 'n/a'})"
            + (f" · disposition: {r.disposition}" if r.disposition else ""),
            f"article: {r.article_title or '—'}",
        ],
        "link": "../artifacts/article_published.md",
    }
