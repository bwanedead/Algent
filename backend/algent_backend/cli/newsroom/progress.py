"""
What a newsroom rail run still has on disk, and what to do next.

A late failure leaves finished work in ``artifacts/``. Resume is the economic move:
take that state and continue from the next unpaid stage. Never re-buy a stage whose
artifact is already there, and never silently regenerate a missing one and call it resume.

``--from STAGE`` is the operator override: reuse everything *before* that stage, redo
that stage and everything after. Default (no override) is "next missing."
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

#: Operator-facing stages, in pipe order. ``publish`` is cheap (render + site); everything
#: before it may spend models/search.
STAGES: tuple[str, ...] = (
    "synthesis",
    "routing",
    "profile",
    "gauntlet",
    "editorial",
    "publish",
)

#: Artifact filename → rail/editorial state key. Presence means that stage's output survived.
_FILES: tuple[tuple[str, str], ...] = (
    ("t0_pool.json", "pool"),
    ("research_portfolio.json", "portfolio"),
    ("selected_vector.json", "selected_vector"),
    ("profile.json", "profile"),
    ("gauntlet_report.json", "gauntlet"),
    ("treatment.json", "treatment"),
    ("planning_gauntlet_report.json", "plan_report"),
    ("draft.json", "draft"),
    ("drafting_gauntlet_report.json", "draft_report"),
    ("hero.json", "hero"),
    ("analytics_plan.json", "analytics_plan"),
    ("analytics_artifacts.json", "analytics_artifacts"),
    ("analytics_confirm_report.json", "analytics_confirm"),
    ("editorial_pipeline_report.json", "pipeline_prior"),
)

#: Keys the rail/pipeline treat as stage outputs. ``--from STAGE`` drops this stage and after.
#: ``pool`` is an input, not an output, so it is never dropped.
STAGE_OUTPUTS: dict[str, tuple[str, ...]] = {
    "synthesis": ("portfolio",),
    "routing": ("selected_vector",),
    "profile": ("profile",),
    "gauntlet": ("gauntlet",),
    "editorial": (
        "treatment", "plan_report", "draft", "draft_report", "hero",
        "analytics_plan", "analytics_artifacts", "analytics_confirm", "pipeline_prior",
    ),
    "publish": (),
}

#: State keys resume must replace (not merge) so a prior continue cannot resurrect a --from drop.
#: ``pool`` is an input, not a stage output — keep the original request's pool when the
#: run never wrote t0_pool.json.
ARTIFACT_STATE_KEYS: frozenset[str] = frozenset(
    key for _name, key in _FILES if key != "pool"
) | frozenset({"source_run_id"})

_SHIPPED = frozenset({"published", "corrected", "staged"})


@dataclass(frozen=True)
class Progress:
    """A run's surviving artifacts and the next unpaid move."""

    run: Path
    present: tuple[str, ...]
    state: dict[str, Any]
    next_step: str              # publish | continue | already_done | nothing
    next_stage: str             # first unpaid pipe stage (or "" if done/nothing)
    skip: tuple[str, ...]       # stages the rail/pipeline will not re-run
    note: str = ""
    published: bool = False
    article_published: bool = False


def runs_root() -> Path:
    from algent_backend.agent_system.runs.control_plane.layout import runs_data_root

    return runs_data_root() / "newsroom_rail"


def run_id_of(run: Path) -> str:
    state_file = run / "state.json"
    if state_file.is_file():
        try:
            rid = json.loads(state_file.read_text(encoding="utf-8")).get("run_id")
            if rid:
                return str(rid)
        except (OSError, ValueError, json.JSONDecodeError):
            pass
    name = run.name
    return name.split("__", 1)[1] if "__" in name else name


def load_json(path: Path) -> Any:
    from algent_backend.agent_system.foundation.text_hygiene import scrub

    return scrub(json.loads(path.read_text(encoding="utf-8")))


def _load_artifacts(arts: Path) -> dict[str, Any]:
    out: dict[str, Any] = {}
    for name, key in _FILES:
        path = arts / name
        if not path.is_file():
            continue
        try:
            out[key] = load_json(path)
        except (OSError, ValueError, json.JSONDecodeError):
            continue
    return out


def _from_drops(from_stage: str) -> frozenset[str]:
    drop: list[str] = []
    started = False
    for stage in STAGES:
        if stage == from_stage:
            started = True
        if started:
            drop.extend(STAGE_OUTPUTS[stage])
    return frozenset(drop)


def gauntlet_done(blob: Any) -> bool:
    """Same predicate the rail uses: a verdict, not merely a nested dict."""
    if not isinstance(blob, dict):
        return False
    inner = blob.get("gauntlet") if isinstance(blob.get("gauntlet"), dict) else None
    if inner and inner.get("final_verdict"):
        return True
    return bool(blob.get("final_verdict"))


def _analytics_unfulfilled(state: dict[str, Any]) -> bool:
    """True when a visual plan is still open and the worker never wrote artifacts."""
    if "analytics_artifacts" in state:
        return False
    plan = state.get("analytics_plan") or {}
    if not isinstance(plan, dict) or not plan.get("warranted"):
        return False
    deferred = frozenset({
        "not_warranted", "soft_cap_skipped", "worker_disabled", "source_unavailable",
    })
    for req in plan.get("requests") or []:
        if not isinstance(req, dict):
            continue
        status = str(req.get("status") or "requested").strip().lower() or "requested"
        if status not in deferred:
            return True
    return False


def _shipped(run: Path, arts: Path) -> bool:
    report_path = arts / "newsroom_rail_report.json"
    if not report_path.is_file():
        return False
    try:
        report = load_json(report_path)
    except (OSError, ValueError, json.JSONDecodeError):
        return False
    if not isinstance(report, dict):
        return False
    if report.get("published"):
        return True
    return str(report.get("publish_action") or "") in _SHIPPED


def _next_unpaid(state: dict[str, Any]) -> str:
    """First pipe stage whose output is missing. Empty string = editorial output is on disk."""
    portfolio = state.get("portfolio") if isinstance(state.get("portfolio"), dict) else {}
    vector = state.get("selected_vector") if isinstance(state.get("selected_vector"), dict) else {}
    profile = state.get("profile") if isinstance(state.get("profile"), dict) else {}
    gauntlet = state.get("gauntlet") if isinstance(state.get("gauntlet"), dict) else {}
    draft = state.get("draft") if isinstance(state.get("draft"), dict) else {}

    if not (portfolio or {}).get("vectors") and not profile.get("id") and not vector.get("id"):
        if state.get("pool"):
            return "synthesis"
        return ""
    if not profile.get("id") and not vector.get("id"):
        return "routing"
    if not profile.get("id"):
        return "profile"
    if not gauntlet_done(gauntlet):
        return "gauntlet"
    if not draft.get("id") or _analytics_unfulfilled(state):
        return "editorial"
    return "publish"


def _skips(state: dict[str, Any]) -> tuple[str, ...]:
    out: list[str] = []
    portfolio = state.get("portfolio") if isinstance(state.get("portfolio"), dict) else {}
    vector = state.get("selected_vector") if isinstance(state.get("selected_vector"), dict) else {}
    profile = state.get("profile") if isinstance(state.get("profile"), dict) else {}
    gauntlet = state.get("gauntlet") if isinstance(state.get("gauntlet"), dict) else {}
    treatment = state.get("treatment") if isinstance(state.get("treatment"), dict) else {}
    draft = state.get("draft") if isinstance(state.get("draft"), dict) else {}
    if (portfolio or {}).get("vectors") or profile.get("id") or vector.get("id"):
        out.append("synthesis")
    if profile.get("id") or vector.get("id"):
        out.append("routing")
    if profile.get("id"):
        out.append("profile")
    if gauntlet_done(gauntlet):
        out.append("gauntlet")
    if treatment.get("id"):
        out.append("planning")
    if draft.get("id"):
        out.append("drafting")
    if "analytics_plan" in state:
        out.append("analytics_plan")
    if "analytics_artifacts" in state:
        out.append("analytics_worker")
    if "analytics_confirm" in state:
        out.append("analytics_confirm")
    return tuple(out)


def assess(run: Path, *, from_stage: str | None = None) -> Progress:
    """Read a run directory and decide the next unpaid move."""
    arts = run / "artifacts"
    raw = _load_artifacts(arts) if arts.is_dir() else {}
    if from_stage:
        if from_stage not in STAGES:
            raise ValueError(f"unknown stage {from_stage!r} — choose one of {', '.join(STAGES)}")
        drop = _from_drops(from_stage)
        raw = {k: v for k, v in raw.items() if k not in drop}

    article_published = (arts / "article_published.md").is_file() and from_stage != "editorial"
    shipped = _shipped(run, arts) and not from_stage
    present = tuple(key for _name, key in _FILES if key in raw)

    state = dict(raw)
    state["source_run_id"] = run_id_of(run)

    if from_stage == "publish":
        next_stage = "publish"
    elif from_stage:
        next_stage = from_stage
    else:
        next_stage = _next_unpaid(state)

    profile = state.get("profile") if isinstance(state.get("profile"), dict) else {}
    draft = state.get("draft") if isinstance(state.get("draft"), dict) else {}
    skip = _skips(state)

    if not raw and not (arts.is_dir() and any(arts.iterdir())):
        return Progress(
            run=run, present=present, state=state, next_step="nothing",
            next_stage="", skip=(), note="no artifacts on disk",
            article_published=article_published, published=shipped,
        )

    if shipped and not from_stage:
        return Progress(
            run=run, present=present, state=state, next_step="already_done",
            next_stage="", skip=skip, note="already published",
            article_published=article_published, published=True,
        )

    if next_stage == "publish" and draft.get("id"):
        return Progress(
            run=run, present=present, state=state, next_step="publish",
            next_stage="publish", skip=skip,
            note="draft on disk — render and publish, no model spend",
            article_published=article_published, published=shipped,
        )

    if next_stage in STAGES:
        if next_stage in ("profile", "gauntlet", "editorial", "publish") and not (
            profile.get("id") or (state.get("selected_vector") or {}).get("id")
            or (state.get("portfolio") or {}).get("vectors")
        ):
            return Progress(
                run=run, present=present, state=state, next_step="nothing",
                next_stage=next_stage, skip=skip,
                note=f"cannot resume at {next_stage} — no portfolio, vector, or profile on disk",
                article_published=article_published, published=shipped,
            )
        return Progress(
            run=run, present=present, state=state, next_step="continue",
            next_stage=next_stage, skip=skip,
            note=f"continue from {next_stage} — reuse {', '.join(skip) or 'nothing yet'}",
            article_published=article_published, published=shipped,
        )

    if draft.get("id"):
        return Progress(
            run=run, present=present, state=state, next_step="publish",
            next_stage="publish", skip=skip,
            note="draft on disk — render and publish, no model spend",
            article_published=article_published, published=shipped,
        )

    return Progress(
        run=run, present=present, state=state, next_step="nothing",
        next_stage="", skip=skip, note="nothing resumable",
        article_published=article_published, published=shipped,
    )


def latest_resumable(root: Path | None = None) -> Path | None:
    """Newest rail run that is not already shipped."""
    base = root or runs_root()
    if not base.is_dir():
        return None
    candidates: list[Path] = []
    for run in base.glob("*/"):
        if not run.is_dir() or run.name.startswith(("_", ".")):
            continue
        progress = assess(run)
        if progress.next_step in ("publish", "continue"):
            candidates.append(run)
    return max(candidates, key=lambda p: p.stat().st_mtime) if candidates else None


def summary(progress: Progress) -> dict[str, Any]:
    return {
        "run": progress.run.name,
        "next_step": progress.next_step,
        "next_stage": progress.next_stage,
        "skip": list(progress.skip),
        "present": list(progress.present),
        "note": progress.note,
        "article_published": progress.article_published,
        "published": progress.published,
    }


def rail_input(state: dict[str, Any]) -> dict[str, Any]:
    """State keys the rail graph actually consumes — drop assess-only bookkeeping."""
    return {k: v for k, v in state.items() if not str(k).startswith("_")}


def inject_state(existing_input: dict[str, Any], state: dict[str, Any]) -> dict[str, Any]:
    """Replace artifact keys rather than merge, so a prior continue cannot undo ``--from``."""
    kept = {k: v for k, v in existing_input.items() if k not in ARTIFACT_STATE_KEYS}
    return {**kept, **rail_input(state)}
