"""
The analytics worker — fulfills one grounded ``AnalyticsRequest`` into a real artifact.

The router decides a chart/table/insight/illustration would help and emits a request grounded in
the profile's data (by id). This stage BUILDS it, by handing the request + exactly its cited data
to a sandboxed grok-build subprocess that draws the visual inside ``analytics_workspace/`` and
nothing else (see that dir's ``AGENTS.md`` for the worker's doctrine).

Integrity is the HARNESS's job, not the worker's — mechanical, not doctrinal (so a misbehaving
subprocess can't launder its way past it):
  1. the subprocess runs with ``cwd`` pinned to a per-request scratch folder under the workspace;
  2. a post-run SWEEP enforces an artifact-type allowlist (png/svg/csv/md) and a size cap,
     deleting anything else the subprocess left;
  3. a FIGURE CHECK diffs the numbers in the produced data table against the cited claims — the
     visual analog of ``unverified_prose_figures`` (a chart can drift off its evidence too);
  4. the harness (not the worker) copies the finished artifact OUT into the run's artifact store,
     stamps provenance (claim ids, as-of, an AI label), then EMPTIES the scratch folder.

So the worker draws; the harness decides what — if anything — is trustworthy enough to publish.
"""

from __future__ import annotations

import re
import shutil
import subprocess
import time
from collections.abc import Callable
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, TypedDict

from langchain_core.runnables import RunnableConfig
from langgraph.graph import END, START, StateGraph

from algent_backend.agent_system.agents.research.profile import Claim, SignalProfile
from algent_backend.agent_system.runs.context import AgentRunContext

from .analytics_contracts import (
    AI_ANALYTIC_LABEL,
    AnalyticsArtifact,
    AnalyticsPlan,
    AnalyticsRequest,
)

GENERATOR = "analytics_worker@v1"
ANALYTICS_WORKER_COMPLETED = "analytics_worker.completed"
ANALYTICS_ARTIFACT_PRODUCED = "analytics_worker.artifact"
ANALYTICS_WORKER_ESCAPE = "analytics_worker.escape"   # loud: the worker wrote outside its lane
ANALYTICS_WORKER_READY = "analytics_worker.ready"     # update + canary result, before any spend

# The sandbox: a per-request scratch folder lives under here; AGENTS.md at its root carries the
# worker doctrine (discovered by grok walking up from the scratch cwd).
_WORKSPACE_DIRNAME = "analytics_workspace"

# The gitignored content stores the git tripwire is BLIND to (git status --porcelain omits ignored
# paths) — and precisely the pipeline-poisoning targets: overwrite one profile/treatment/draft JSON
# and every downstream stage inherits the corruption. So we fingerprint them separately. Small-JSON
# dirs, cheap to stat; NOT runs_data (the run's own legitimately-churning control plane) or
# ingestion_data (large, and not a per-request corruption target).
_GUARDED_STORE_DIRS = ("profile_store", "treatment_store", "draft_store", "lead_store")

# The artifact-type allowlist + size cap the post-run sweep enforces (mechanical, not doctrinal).
_ALLOWED_SUFFIXES = {".png", ".svg", ".csv", ".md", ".json", ".txt"}
_MAX_FILE_BYTES = 2_000_000       # a chart/table is small; anything large is a red flag
_MAX_TOTAL_BYTES = 8_000_000

# What the worker is told to emit (by kind). The harness looks for exactly these.
_VISUAL_NAMES = {"chart": ("chart.svg", "chart.png"), "image": ("illustration.svg", "illustration.png"),
                 "table": ("table.md",), "insight": ("insight.md",)}
_DATA_NAME = "data.csv"
_CAPTION_NAME = "caption.md"

_TIMEOUT_S = 240.0

# A measured quantity: a percentage or a decimal — the values a chart could FABRICATE. Bare
# integers are deliberately excluded: they are the axis/date labels (years, month numbers,
# category counts) that are not themselves evidence claims, and catching them cries wolf on every
# time axis. This mirrors unverified_prose_figures' stance (percentages only; counts fall to the
# semantic judge) — err toward missing a drift, never toward inventing one.
_SIG_NUM = re.compile(r"\d+\.\d+%?|\d+%")


_STALE_SCRATCH_AGE_S = 2 * 60 * 60   # a live request's scratch is minutes old, never hours


def sweep_stale_scratch(workspace: Path, *, max_age_s: float = _STALE_SCRATCH_AGE_S) -> list[str]:
    """Remove per-request scratch dirs orphaned by a killed run. Returns what it cleaned.

    ``fulfill_request`` empties its scratch in a ``finally``, but a killed process (a dropped
    session, a machine sleep) never runs it — so the workspace slowly accumulates dead folders.
    This self-heals on the next worker start: no daemon, no bookkeeping, no coordination.

    Age-gated rather than sweeping everything, so a CONCURRENT run's live scratch is never deleted:
    an in-flight request's folder is minutes old; anything hours old belongs to a run that is gone.
    """
    cleaned: list[str] = []
    if not workspace.is_dir():
        return cleaned
    cutoff = time.time() - max_age_s
    for child in workspace.iterdir():
        if not child.is_dir() or child.name.startswith("."):
            continue
        try:
            if child.stat().st_mtime < cutoff:
                shutil.rmtree(child, ignore_errors=True)
                cleaned.append(child.name)
        except OSError:
            continue
    return cleaned


def default_workspace() -> Path:
    """The repo-root ``analytics_workspace/`` (5 up: editorial→agents→agent_system→algent_backend→backend→root)."""
    return Path(__file__).resolve().parents[5] / _WORKSPACE_DIRNAME


# ── the grounded hand-off ────────────────────────────────────────────────────────────────────

def _grounded_data(request: AnalyticsRequest, profile: SignalProfile) -> tuple[dict[str, Any], list[Claim], str]:
    """Resolve the request's ``data_refs`` to the profile's ACTUAL items — the only data the worker sees.

    Returns (payload for data.json, the cited claim objects for the figure check, the as-of date).
    """
    claims_by_id = {c.id: c for c in profile.claim_ledger}
    sources_by_id = {s.id: s for s in profile.source_ledger}
    threads_by_id = {t.id: t for t in profile.threads}
    refs = set(request.data_refs)

    cited_claims = [claims_by_id[i] for i in request.data_refs if i in claims_by_id]
    claims = [{"id": c.id, "text": c.text, "status": c.status, "grounding": c.grounding} for c in cited_claims]
    threads = [{"id": t.id, "title": t.title, "body": t.body}
               for tid, t in threads_by_id.items() if tid in refs]
    sources = [{"id": s.id, "title": s.title, "publisher": s.publisher, "url": s.url,
                "published_at": s.published_at} for sid, s in sources_by_id.items() if sid in refs]
    # A source cited only THROUGH a claim still belongs in the provenance the caption will carry.
    for c in cited_claims:
        for sid in c.supported_by:
            s = sources_by_id.get(sid)
            if s and not any(x["id"] == sid for x in sources):
                sources.append({"id": s.id, "title": s.title, "publisher": s.publisher,
                                "url": s.url, "published_at": s.published_at})

    payload = {
        "request_id": request.id, "kind": request.kind, "title": request.title,
        "question": request.question, "spec": request.spec, "rationale": request.rationale,
        "as_of": profile.as_of, "claims": claims, "threads": threads, "sources": sources,
    }
    return payload, cited_claims, profile.as_of


def _brief(request: AnalyticsRequest) -> str:
    """The human/agent-readable request the worker reads alongside data.json."""
    names = _VISUAL_NAMES.get(request.kind, ("output.md",))
    return "\n".join([
        f"# Analytics request — {request.id} ({request.kind})",
        f"\n**Title:** {request.title}",
        f"**What the reader should learn:** {request.question}",
        f"**Build:** {request.spec}",
        f"**Why it helps:** {request.rationale}",
        "\n## Your job",
        "Build EXACTLY this one analytic, using ONLY the data in `data.json` (already fetched and",
        "cited — do not go find more). Follow the doctrine in `AGENTS.md`. Then emit:",
        f"- `{names[0]}`" + (f" (or `{names[1]}`)" if len(names) > 1 else "") + " — the analytic itself",
        f"- `{_DATA_NAME}` — the exact rows you plotted (so the harness can verify the numbers)",
        f"- `{_CAPTION_NAME}` — one or two plain sentences describing what it shows",
        "\nIf the data is too thin, contested, or would force a misleading visual: do NOT improvise —",
        "write `SKIPPED.md` with the reason instead. Faithful and bounded beats clever.",
    ]) + "\n"


def _prompt() -> str:
    return ("Read AGENTS.md, REQUEST.md, and data.json in this folder, then build the one requested "
            "analytic from ONLY the data in data.json and write the output files REQUEST.md asks for. "
            "Do not fetch anything, do not install heavy packages, do not write outside this folder.")


# ── the mechanical guardrails (harness-owned) ────────────────────────────────────────────────

def _sweep(folder: Path) -> list[str]:
    """Enforce the artifact-type allowlist + size cap; delete + report anything outside it."""
    removed: list[str] = []
    total = 0
    for p in sorted(folder.rglob("*")):
        if p.is_dir():
            continue
        too_big = p.stat().st_size > _MAX_FILE_BYTES
        if p.suffix.lower() not in _ALLOWED_SUFFIXES or too_big:
            removed.append(p.name + (" (oversized)" if too_big and p.suffix.lower() in _ALLOWED_SUFFIXES else ""))
            p.unlink(missing_ok=True)
            continue
        total += p.stat().st_size
    if total > _MAX_TOTAL_BYTES:                       # belt-and-suspenders: refuse a bloated batch
        for p in folder.rglob("*"):
            if p.is_file():
                p.unlink(missing_ok=True)
        removed.append(f"ALL (total {total}B over cap)")
    return removed


def _git_status(root: Path) -> set[str] | None:
    """Repo-relative paths currently dirty in ``root`` — the tripwire baseline.

    Excludes ``analytics_workspace/`` itself (the worker's legitimate, gitignored home). Returns
    None when ``root`` is not a git repo or git is unavailable — the tripwire then simply doesn't
    arm (it is a free bonus check, never a hard dependency of the worker).

    BLIND SPOT: ``git status`` omits gitignored paths, so a worker that overwrote a gitignored
    store JSON would not surface here. ``_store_fingerprint`` covers exactly those stores; the two
    checks are complementary and both feed the escape decision.
    """
    try:
        proc = subprocess.run(
            ["git", "-C", str(root), "status", "--porcelain"],
            capture_output=True, text=True, timeout=15, encoding="utf-8", errors="replace",
        )
    except (FileNotFoundError, OSError, subprocess.SubprocessError):
        return None
    if proc.returncode != 0:
        return None
    paths: set[str] = set()
    for line in proc.stdout.splitlines():
        p = line[3:].strip().split(" -> ")[-1].strip('"')   # drop the XY prefix; take a rename's dest
        if p and not p.startswith((_WORKSPACE_DIRNAME + "/", _WORKSPACE_DIRNAME + "\\")):
            paths.add(p)
    return paths


def _new_escapes(before: set[str] | None, after: set[str] | None) -> list[str]:
    """Paths that became dirty DURING the worker run, outside its lane — a detected escape.

    Diffed against a baseline so the user's own pre-existing uncommitted work never trips it.
    """
    if before is None or after is None:
        return []
    return sorted(after - before)


def _store_fingerprint(repo_root: Path) -> dict[str, tuple[int, int]]:
    """(mtime_ns, size) of the guarded gitignored files — the git tripwire's blind spot. Cheap:
    small per-item JSON, not dependency-scale trees. Covers the content stores AND ``.env`` files
    (credential poisoning is the classic sandbox escape, and ``.env`` is gitignored + not a store,
    so nothing else would catch it). Metadata only — NEVER reads any file's contents."""
    fp: dict[str, tuple[int, int]] = {}

    def _stamp(p: Path) -> None:
        try:
            st = p.stat()
            fp[str(p)] = (st.st_mtime_ns, st.st_size)
        except OSError:
            pass

    for name in _GUARDED_STORE_DIRS:
        d = repo_root / "backend" / name
        if d.is_dir():
            for p in d.rglob("*"):
                if p.is_file():
                    _stamp(p)
    # .env at the repo root and under backend/ — mtime+size only, contents never touched.
    for base in (repo_root, repo_root / "backend"):
        for p in (*base.glob(".env"), *base.glob(".env.*")):
            if p.is_file():
                _stamp(p)
    return fp


def _store_escapes(before: dict[str, tuple[int, int]], after: dict[str, tuple[int, int]]) -> list[str]:
    """Store files created OR modified during the run — a worker corrupting the pipeline's state.

    Baseline-diffed like the git check: any pre-existing file that legitimately changed outside the
    run window cancels; only a write during the run surfaces. Reports the offending file paths.
    """
    return sorted(k for k, v in after.items() if before.get(k) != v)


def _visual_unverified_figures(data_text: str, cited_claims: list[Claim], sources_by_id: dict) -> list[str]:
    """Significant numbers in the plotted data that appear NOWHERE in the cited evidence — the
    visual analog of ``unverified_prose_figures``. Same conservative stance (substring, err toward
    missing a drift rather than inventing one)."""
    corpus = " ".join(c.text for c in cited_claims)
    for c in cited_claims:
        for sid in c.supported_by:
            s = sources_by_id.get(sid)
            if s and s.snapshot and s.snapshot.excerpt:
                corpus += " " + s.snapshot.excerpt
    return [n for n in dict.fromkeys(_SIG_NUM.findall(data_text)) if n not in corpus]


def _collect(folder: Path, kind: str) -> tuple[Path | None, Path | None, str]:
    """Find the produced (visual, data, caption) after the sweep. visual/data may be None (a skip/fail)."""
    visual = next((folder / n for n in _VISUAL_NAMES.get(kind, ()) if (folder / n).exists()), None)
    data = folder / _DATA_NAME if (folder / _DATA_NAME).exists() else None
    cap = (folder / _CAPTION_NAME).read_text(encoding="utf-8").strip() if (folder / _CAPTION_NAME).exists() else ""
    return visual, data, cap


def _caption(request: AnalyticsRequest, worker_caption: str, data_refs: list[str], as_of: str) -> str:
    """Harness-assembled caption: the worker's description + provenance the harness controls."""
    base = worker_caption or request.title or request.question
    prov = f"Source: cited claims {', '.join(data_refs)}." if data_refs else ""
    asof = f" As of {as_of}." if as_of else ""
    return f"{base} — {AI_ANALYTIC_LABEL}. {prov}{asof}".strip()


# ── the runner (injectable so tests never spawn a subprocess) ─────────────────────────────────

def _grok_runner(prompt: str, folder: Path, *, timeout: float) -> tuple[bool, str]:
    """Run grok-build headless, cwd pinned to the scratch folder. Returns (ok, tail-of-output)."""
    try:
        proc = subprocess.run(
            ["grok", "-p", prompt, "--cwd", str(folder), "--output-format", "json",
             "--always-approve", "--disable-web-search", "--no-memory"],
            capture_output=True, text=True, timeout=timeout,
            # grok emits UTF-8 (smart quotes / emoji); decode as such so Windows' cp1252 locale
            # can't crash the decode. errors='replace' keeps a garbled tail from ever raising.
            encoding="utf-8", errors="replace",
        )
    except FileNotFoundError:
        return False, "grok CLI not found on PATH"
    except subprocess.TimeoutExpired:
        return False, f"grok timed out after {timeout}s"
    out = (proc.stdout or "")[-600:] + (("\n" + proc.stderr[-300:]) if proc.stderr else "")
    return proc.returncode == 0, out


Runner = Callable[[str, Path], tuple[bool, str]]


def grok_version() -> str:
    """The exact harness version — stamped onto every artifact as provenance, so a shift in
    analytics quality can be correlated to a tool version from the ledger instead of guessed."""
    try:
        proc = subprocess.run(["grok", "--version"], capture_output=True, text=True, timeout=30,
                              encoding="utf-8", errors="replace")
        return (proc.stdout or "").strip() or "unknown"
    except (FileNotFoundError, OSError, subprocess.SubprocessError):
        return "unknown"


def update_grok() -> str:
    """Update the harness AT A RUN BOUNDARY (never mid-run — one tool version per article).

    The harness's improvement curve IS the analytics quality curve, so we take the newest build
    every run rather than pinning. This is affordable precisely because analytics degrade
    gracefully: a bad release costs one missing visual, never a broken article (contrast the
    drafter's model, where the same policy would be reckless).
    """
    try:
        proc = subprocess.run(["grok", "update"], capture_output=True, text=True, timeout=180,
                              encoding="utf-8", errors="replace")
        out = ((proc.stdout or "") + (proc.stderr or "")).strip().splitlines()
        return (out[-1][:160] if out else "updated") if proc.returncode == 0 else "update failed"
    except (FileNotFoundError, OSError, subprocess.SubprocessError) as exc:
        return f"update skipped ({str(exc)[:60]})"


def canary(workspace: Path, *, runner: Runner | None = None, timeout: float = 120.0) -> tuple[bool, str]:
    """Prove the freshly-updated harness still works, on fixture data, before spending on real work.

    Seconds of quota: draw one tiny chart from known numbers and check an artifact came back. A
    pass means the new build behaves; a fail means we skip analytics for this run and SAY SO,
    rather than discovering the breakage halfway through an article's visuals.
    """
    folder = workspace / "_canary"
    shutil.rmtree(folder, ignore_errors=True)
    folder.mkdir(parents=True, exist_ok=True)
    try:
        (folder / "data.csv").write_text("month,value\nMar,1.0\nApr,2.0\nMay,3.0\n", encoding="utf-8")
        prompt = ("Read data.csv in this folder and draw a minimal line chart of value by month as "
                  "chart.svg. Nothing else — no extra files, no network.")
        ok, tail = (runner or (lambda p, f: _grok_runner(p, f, timeout=timeout)))(prompt, folder)
        drew = (folder / "chart.svg").exists() or (folder / "chart.png").exists()
        if drew:
            return True, "canary ok"
        return False, f"canary produced no chart ({'ran' if ok else 'run failed'}: {tail[:100]})"
    finally:
        shutil.rmtree(folder, ignore_errors=True)


def fulfill_request(
    request: AnalyticsRequest,
    profile: SignalProfile,
    *,
    workspace: Path | None = None,
    context: AgentRunContext | None = None,
    runner: Runner | None = None,
    timeout: float = _TIMEOUT_S,
    version: str = "",
) -> AnalyticsArtifact:
    """Build one grounded request into an artifact, with the harness owning integrity end-to-end."""
    workspace = workspace or default_workspace()
    payload, cited_claims, as_of = _grounded_data(request, profile)
    result = AnalyticsArtifact(request_id=request.id, kind=request.kind, title=request.title,
                               question=request.question,
                               data_refs=request.data_refs, as_of=as_of,
                               generator=GENERATOR, model=version or "grok-build",
                               generated_at=datetime.now(UTC).isoformat())

    if not request.data_refs:                          # the router should have filtered this; belt-and-suspenders
        return result.model_copy(update={"status": "failed", "note": "no grounded data_refs"})

    folder = workspace / _safe(request.id)
    if folder.exists():
        shutil.rmtree(folder, ignore_errors=True)
    folder.mkdir(parents=True, exist_ok=True)
    repo_root = workspace.parent                        # analytics_workspace/ sits at the repo root
    try:
        import json
        (folder / "data.json").write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
        (folder / "REQUEST.md").write_text(_brief(request), encoding="utf-8")

        before_git = _git_status(repo_root)             # tripwire baseline (see _git_status)
        before_store = _store_fingerprint(repo_root)    # + the gitignored stores git can't see
        ok, tail = (runner or (lambda p, f: _grok_runner(p, f, timeout=timeout)))(_prompt(), folder)

        removed = _sweep(folder)                        # (2) artifact-type + size sweep

        # (2b) ESCAPE tripwire — "stay in your lane" as a DETECTED invariant, not just doctrine. If
        # the worker wrote anything in the repo outside analytics_workspace/ — tracked files (git)
        # OR the gitignored content stores it could poison — distrust it entirely (a good-looking
        # chart from a lane-breaking run is not trustworthy) and alert loudly.
        escaped = (_new_escapes(before_git, _git_status(repo_root))
                   + _store_escapes(before_store, _store_fingerprint(repo_root)))
        if escaped:
            if context is not None:
                context.emit(ANALYTICS_WORKER_ESCAPE, {"request_id": request.id, "escaped": escaped})
            return _finalize(result, status="failed", swept=removed, escaped_writes=escaped,
                             note="worker wrote outside analytics_workspace/: " + ", ".join(escaped[:5]))

        skipped = (folder / "SKIPPED.md")
        if skipped.exists():
            return _finalize(result, status="skipped", swept=removed,
                             note=skipped.read_text(encoding="utf-8")[:300].strip())

        visual, data, worker_cap = _collect(folder, request.kind)
        if not ok and visual is None:
            return _finalize(result, status="failed", swept=removed, note=f"worker produced nothing ({tail[:180]})")
        if visual is None:
            return _finalize(result, status="failed", swept=removed, note="no output artifact found")

        # (3) figure check — the visual analog of unverified_prose_figures.
        data_text = data.read_text(encoding="utf-8", errors="replace") if data else ""
        sources_by_id = {s.id: s for s in profile.source_ledger}
        unverified = _visual_unverified_figures(data_text, cited_claims, sources_by_id) if data_text else []
        figure_check = {"checked": bool(data_text), "verified": data_text != "" and not unverified,
                        "unverified": unverified}

        # A markdown analytic (table/insight) is INLINED by the publish view, not embedded as an
        # image — so carry its body forward. An image analytic (chart/illustration) has no body.
        body_md = visual.read_text(encoding="utf-8", errors="replace") if visual.suffix == ".md" else ""

        # (4) copy the finished artifact OUT (harness, not worker) + stamp provenance.
        artifact_name = data_name = ""
        if context is not None and context.artifacts is not None:
            artifact_name = f"analytic_{_safe(request.id)}{visual.suffix}"
            context.artifacts.write_bytes(artifact_name, visual.read_bytes(), kind="analytic")
            if data:
                data_name = f"analytic_{_safe(request.id)}_data.csv"
                context.artifacts.write_text(data_name, data_text, kind="analytic_data")

        return _finalize(
            result, status="produced", swept=removed,
            artifact_name=artifact_name or visual.name, data_name=data_name or (data.name if data else ""),
            body_md=body_md,
            caption=_caption(request, worker_cap, request.data_refs, as_of),
            figure_check=figure_check,
            note=("figure check: numbers not found in cited evidence — " + ", ".join(unverified)) if unverified else "",
        )
    finally:
        shutil.rmtree(folder, ignore_errors=True)       # (1)+(4) empty the scratch folder, always


def _finalize(result: AnalyticsArtifact, **updates: Any) -> AnalyticsArtifact:
    return result.model_copy(update=updates)


def _safe(name: str) -> str:
    return re.sub(r"[^A-Za-z0-9._-]+", "_", name).strip("._") or "request"


# ── the pipeline stage ────────────────────────────────────────────────────────────────────────

class WorkerState(TypedDict, total=False):
    analytics_plan: dict[str, Any]      # the router's plan (input)
    profile: dict[str, Any]             # the profile the plan is grounded in (input)
    analytics_artifacts: list[dict[str, Any]]


def build_analytics_worker_graph(
    context: AgentRunContext, *, runner: Runner | None = None, refresh: bool = True,
) -> Any:
    """Compile the worker stage: fulfill each warranted request in a plan into an artifact.

    ``runner`` is injectable (tests pass a fake); the default spawns grok-build. ``refresh``
    updates the harness at this run boundary + canaries it before any real spend (tests pass False).
    """

    def work(state: WorkerState, config: RunnableConfig) -> dict[str, Any]:
        plan_dict = state.get("analytics_plan") or {}
        plan = AnalyticsPlan.model_validate(plan_dict) if plan_dict else AnalyticsPlan(id="analytics_none")
        pdict = state.get("profile")
        if not plan.warranted or not plan.requests or not pdict:
            context.emit(ANALYTICS_WORKER_COMPLETED, {"produced": 0, "note": "nothing warranted"})
            return {"analytics_artifacts": []}

        # Take the newest harness at the RUN BOUNDARY (never mid-run: one tool version per
        # article), then prove it still works on fixture data before spending on real requests.
        # A bad release costs this run's visuals, not the article — that graceful degradation is
        # exactly what makes an always-update policy affordable here.
        version = ""
        if refresh:
            # Self-heal first: a killed run can't empty its own scratch, so clean up anything a
            # dead predecessor left behind before adding more.
            cleaned = sweep_stale_scratch(default_workspace())
            note = update_grok()
            version = grok_version()
            ok, canary_note = canary(default_workspace(), runner=runner)
            context.emit(ANALYTICS_WORKER_READY, {"version": version, "update": note,
                                                  "canary": canary_note, "swept_stale": cleaned})
            if not ok:
                context.emit(ANALYTICS_WORKER_COMPLETED, {
                    "produced": 0, "note": f"analytics skipped — {canary_note} (version {version})"})
                return {"analytics_artifacts": []}

        profile = SignalProfile.model_validate(pdict)
        artifacts: list[AnalyticsArtifact] = []
        for request in plan.requests:
            art = fulfill_request(request, profile, context=context, runner=runner, version=version)
            artifacts.append(art)
            context.emit(ANALYTICS_ARTIFACT_PRODUCED, {
                "request_id": art.request_id, "status": art.status,
                "figure_verified": art.figure_check.get("verified"), "note": art.note,
            })

        dumped = [a.model_dump() for a in artifacts]
        if context.artifacts is not None:
            context.artifacts.write_json("analytics_artifacts.json", dumped)
        produced = sum(1 for a in artifacts if a.status == "produced")
        context.emit(ANALYTICS_WORKER_COMPLETED, {"produced": produced, "total": len(artifacts)})
        return {"analytics_artifacts": dumped}

    graph = StateGraph(WorkerState)
    graph.add_node("work", work)
    graph.add_edge(START, "work")
    graph.add_edge("work", END)
    return graph.compile()
