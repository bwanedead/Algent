"""
The analytics worker — fulfills one grounded ``AnalyticsRequest`` into a real artifact.

The router decides a chart/table/insight/illustration would help and emits a request — either
grounded in profile claim ids, or marked ``may_source`` so this stage may fetch public data at
figure time (profile and analytics are separate concerns). This stage BUILDS it via a sandboxed
grok-build subprocess inside ``analytics_workspace/`` (see that dir's ``AGENTS.md``).

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
    AI_ANALYTIC_LABEL_SOURCED,
    AnalyticsArtifact,
    AnalyticsPlan,
    AnalyticsRequest,
)
from .analytics_harness import resolve_harness

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
_ALLOWED_SUFFIXES = {".png", ".svg", ".csv", ".md", ".json", ".txt", ".gif"}
_MAX_FILE_BYTES = 2_500_000       # chart/map/short gif; anything large is a red flag
_MAX_TOTAL_BYTES = 8_000_000

# What the worker is told to emit (by kind). The harness looks for exactly these.
_VISUAL_NAMES = {
    "chart": ("chart.svg", "chart.png", "chart.gif"),
    "image": ("illustration.svg", "illustration.png", "illustration.gif", "map.svg", "map.png"),
    "table": ("table.md",),
    "insight": ("insight.md",),
}
_DATA_NAME = "data.csv"
_CAPTION_NAME = "caption.md"

_TIMEOUT_S = 360.0
# Maps / may_source fetches routinely need longer than a profile-held line chart.
_TIMEOUT_SOURCED_S = 600.0

# A measured quantity: a percentage or a decimal — the values a chart could FABRICATE. Bare
# integers are deliberately excluded: they are the axis/date labels (years, month numbers,
# category counts) that are not themselves evidence claims, and catching them cries wolf on every
# time axis. This mirrors unverified_prose_figures' stance (percentages only; counts fall to the
# semantic judge) — err toward missing a drift, never toward inventing one.
_SIG_NUM = re.compile(r"\d+\.\d+%?|\d+%")

#: Years written as floats. The exclusion above only skips bare integers, so a CSV that
#: renders its time column as ``2019.0`` (which is simply what pandas does to a numeric
#: year) sails past it and every year on the axis is reported as an unverified figure —
#: which is precisely how a decade-long trajectory chart was rejected for citing the
#: decade it covered.
_YEAR_LIKE = re.compile(r"^(?:19|20|21)\d{2}\.0+$")
_CORPUS_NUM = re.compile(r"\d+(?:\.\d+)?")


_STALE_SCRATCH_AGE_S = 2 * 60 * 60   # a live request's scratch is minutes old, never hours

# Weight-bearing stack dirs — never age-sweep these even if the scratch allowlist drifts.
_PROTECTED_WORKSPACE_DIRS = frozenset({"lib", "scripts", "data"})


def _is_scratch_dir(name: str) -> bool:
    """True for per-request / canary scratch folders — the only things age-sweep may remove.

    Production ids are ``anx_*`` (router); tests may use ``req_*``. Never treat ``lib`` /
    ``scripts`` / ``data`` as scratch — an earlier bug deleted any old directory and wiped
    the chart helpers after ~2h idle.
    """
    if name in _PROTECTED_WORKSPACE_DIRS or name.startswith("."):
        return False
    return name == "_canary" or name.startswith(("anx_", "req_"))


def sweep_stale_scratch(workspace: Path, *, max_age_s: float = _STALE_SCRATCH_AGE_S) -> list[str]:
    """Remove per-request scratch dirs orphaned by a killed run. Returns what it cleaned.

    ``fulfill_request`` empties its scratch in a ``finally``, but a killed process (a dropped
    session, a machine sleep) never runs it — so the workspace slowly accumulates dead folders.
    This self-heals on the next worker start: no daemon, no bookkeeping, no coordination.

    Age-gated rather than sweeping everything, so a CONCURRENT run's live scratch is never deleted:
    an in-flight request's folder is minutes old; anything hours old belongs to a run that is gone.

    Only scratch-shaped directories (``anx_*``, ``req_*``, ``_canary``) are candidates.
    ``lib/``, ``scripts/``, and ``data/`` are never removed here regardless of mtime.
    """
    cleaned: list[str] = []
    if not workspace.is_dir():
        return cleaned
    cutoff = time.time() - max_age_s
    for child in workspace.iterdir():
        if not child.is_dir() or not _is_scratch_dir(child.name):
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


_STACK_FILES = (
    "lib/__init__.py",
    "lib/theme.py",
    "lib/charts.py",
    "lib/maps.py",
    "lib/animate.py",
    "AGENTS.md",
)


def workspace_stack_ready(workspace: Path | None = None) -> tuple[bool, str]:
    """True when the tracked helper stack the worker imports is present on disk.

    ``lib/`` is weight-bearing (see ``analytics_workspace/AGENTS.md``). Deleting it looks like a
    tidy-up but silently disables every map/chart; fail closed with an explicit skip reason.
    """
    root = workspace or default_workspace()
    missing = [rel for rel in _STACK_FILES if not (root / rel).is_file()]
    if not missing:
        return True, ""
    return False, (
        "analytics_workspace missing tracked helpers: "
        + ", ".join(missing)
        + " — restore from git; do not delete lib/ (see analytics_workspace/AGENTS.md)"
    )


# ── the grounded hand-off ────────────────────────────────────────────────────────────────────

def _grounded_data(request: AnalyticsRequest, profile: SignalProfile) -> tuple[dict[str, Any], list[Claim], str]:
    """Build the worker hand-off payload from profile refs and/or a source-at-analytics-time brief.

    Profile-held numbers arrive as resolved claims/sources. Source-at-time asks arrive with
    ``may_source`` + ``source_hint`` so the worker can fetch public data. Returns
    (payload for data.json, cited claim objects for the figure check, the as-of date).
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
        "may_source": bool(request.may_source), "source_hint": request.source_hint,
        "as_of": profile.as_of, "claims": claims, "threads": threads, "sources": sources,
        "story_title": profile.title, "story_summary": (profile.summary or "")[:600],
    }
    return payload, cited_claims, profile.as_of


def _brief(request: AnalyticsRequest) -> str:
    """The human/agent-readable request the worker reads alongside data.json."""
    names = _VISUAL_NAMES.get(request.kind, ("output.md",))
    if request.may_source:
        data_rules = [
            "\n## Your job (source-at-analytics-time)",
            "Build EXACTLY this one analytic. Profile and analytics are separate: the series may",
            "NOT already be in data.json. You MAY fetch public data described by `source_hint`",
            f"in data.json / below — **Source hint:** {request.source_hint or request.spec}",
            "",
            "Rules when sourcing:",
            "- Fetch only what the hint names (official dashboards, statistical releases, primary",
            "  public tables). Prefer primary publishers over secondary rewrites.",
            "- Put every plotted row in `data.csv` and name the publisher + a full `https://` URL",
            "  in `caption.md`. The harness rejects sourced figures without a URL — a table alone",
            "  is not provenance.",
            "- NEVER invent, extrapolate, or smooth numbers. If the series is not findable or is",
            "  contested, write `SKIPPED.md` with the reason — do not improvise a chart.",
            "- You may use any claims/sources already in data.json as context for the story, but",
            "  the plotted series must come from real fetched rows (or profile claims if they",
            "  already hold the series).",
        ]
    else:
        data_rules = [
            "\n## Your job",
            "Build EXACTLY this one analytic, using ONLY the data in `data.json` (already fetched",
            "and cited — do not go find more). Follow the doctrine in `AGENTS.md`.",
        ]
    return "\n".join([
        f"# Analytics request — {request.id} ({request.kind})",
        f"\n**Title (on the figure):** {request.title}",
        f"**What this shows (reader explainer):** {request.question}",
        f"**Build:** {request.spec}",
        f"**Why it helps:** {request.rationale}",
        *data_rules,
        "",
        "Stack (already installed in the workspace — do not pip install):",
        "- Python: `..\\.venv\\Scripts\\python.exe` (Windows) or `../.venv/bin/python` (Unix)",
        "- Helpers: `../lib/` — `lib.charts`, `lib.maps`, `lib.animate`, `lib.theme`",
        "- Basemap: `../data/natural_earth/ne_110m_admin_0_countries.geojson` (maps only)",
        "- Maps: use lib.maps.country_points_map with real lat/lon. Viewport follows the point "
        "cluster (readable theater), not full-country bounds — Russia/Canada/USA full outlines "
        "make multi-city stories unreadable. Never freehand coastlines.",
        "",
        "The figure must land in about THREE SECONDS on a cold house reader who will not study it:",
        "- Chart title = the FINDING in plain words, not the measure. 'Data-centre demand nearly",
        "  doubles by 2030' — not 'EU data-centre electricity use, 2024-2030'. If the title only",
        "  names the axes, the reader has to derive the point, and most will not.",
        "- Annotate the number that carries the story directly on the plot, at the place it happens.",
        "- Every axis labeled with units; series named in human language (no series1/y). Where the",
        "  unit is one a general reader does not hold (TWh, GW), give a comparison in the caption.",
        "- Multi-series: use the AGENTS.md hue-contrast palette (amber + cyan + mauve) — never two",
        "  near-identical browns. Label series DIRECTLY at the end of each line or on each band;",
        "  fall back to a legend only when direct labels would collide. A legend is a lookup table",
        "  the reader has to run in their head.",
        "- Keep it simple enough to read at a glance: few series, one axis, no stacked-everything.",
        "  If the figure needs study, plot a simpler cut of the same data instead.",
        "- EVERYTHING MUST FIT INSIDE THE CANVAS. A published timeline had its right-hand labels",
        "  running off the edge, so the reader got half a word. Use `constrained_layout` or",
        "  `bbox_inches='tight'`, keep long labels short or wrapped, and after saving, confirm no",
        "  text extends past the figure bounds. A clipped label is a failed figure and the harness",
        "  now rejects it, so this costs you the whole attempt.",
        "- On a time axis, do not let one distant point stretch the whole scale: if most of the span",
        "  is empty, break or compress the quiet years and give the space to where events cluster.",
        "- State the UNIT in plain words, and mark each number's STATUS — actual, reported,",
        "  estimated or target. Never place a target beside an actual without saying which is which,",
        "  and never compare a subset to a total without separating them.",
        "- A trajectory needs enough points to show its SHAPE. Two endpoints are a pair, not a trend:",
        "  plot the history running into the present as well as any projection, so the reader can see",
        "  the rate and whether the forecast continues the past curve or breaks from it.",
        "- If a real gap exists in the series, leave it and explain it in the caption; if the public",
        "  series is continuous, fetch the missing period — do not invent points.",
        "- Period or as-of visible on the figure or in the caption.",
        f"- `{_CAPTION_NAME}`: 1–3 sentences — what it shows, the main takeaway, any limit.",
        "  No claim ids, no pipeline jargon.",
        "",
        "Then emit:",
        f"- `{names[0]}`" + (f" (or another allowed name: {', '.join(names)})" if len(names) > 1 else "")
        + " — the analytic itself",
        f"- `{_DATA_NAME}` — the exact rows you plotted (so the harness can verify the numbers)",
        f"- `{_CAPTION_NAME}` — plain-language explainer (see above)",
        "",
        "LOOK AT WHAT YOU MADE BEFORE YOU FINISH. Save the figure, then OPEN THE RENDERED FILE",
        "and read it as a reader who has not seen the data. This step is not optional and it is",
        "not a re-read of your code — every defect below shipped from a script that ran without",
        "error, because a successful matplotlib call says nothing about whether the picture works:",
        "  1. TITLE — does it name the finding in plain words? Published titles that failed:",
        "     'EU data-centre electricity use, 2024-2030' (names the axes, not the point) and",
        "     '279 total DUV systems, 47% immersion' (a reader cannot tell what a DUV system is,",
        "     whether 279 is a year or a total, or whether the bars beside it are actual or target).",
        "     A reader should learn the headline finding from the title alone.",
        "  2. OVERLAP — is any text colliding with another label, a bar, a line, the legend, or",
        "     another title? Competing or duplicated headers, a legend sitting on the data, tick",
        "     labels running into each other: all of these have shipped. Fix by rotating, wrapping,",
        "     shortening, moving, or dropping the element — never by shrinking text to unreadable.",
        "  3. CLIPPING — is every label fully inside the frame, with nothing cut at any edge?",
        "  4. ONE HEADER — the figure carries exactly one title. The article prints its own heading",
        "     and caption above it, so a second title inside the image reads as a stutter.",
        "  5. THE THREE-SECOND TEST — could a reader state what this compares and what the answer is,",
        "     in one sentence, without studying it? If not, simplify the cut of the data and redraw.",
        "If any check fails, FIX IT AND RE-RENDER. Iterate until the file passes, then finish.",
        "",
        "If the data is too thin, contested, or would force a misleading visual: do NOT improvise —",
        "write `SKIPPED.md` with the reason instead. Faithful and bounded beats clever.",
    ]) + "\n"


def _prompt(*, may_source: bool = False) -> str:
    stack = (
        "Use the analytics_workspace venv Python if present "
        "(Windows: ..\\.venv\\Scripts\\python.exe ; Unix: ../.venv/bin/python) and the helpers in "
        "../lib/ (charts, maps, animate, theme). Prefer those over freehand drawing. "
        "Never pip install. Never write outside analytics_workspace/. "
    )
    if may_source:
        return (
            "Read AGENTS.md (parent folder), REQUEST.md, and data.json in this folder. Build the "
            "one requested analytic. " + stack +
            "You may fetch public data named by source_hint / REQUEST.md — put every plotted row "
            "in data.csv and name the publisher in caption.md. Never invent numbers. Write the "
            "output files REQUEST.md asks for."
        )
    return (
        "Read AGENTS.md (parent folder), REQUEST.md, and data.json in this folder, then build the "
        "one requested analytic from ONLY the data in data.json and write the output files "
        "REQUEST.md asks for. " + stack +
        "Do not fetch anything."
    )


# ── the mechanical guardrails (harness-owned) ────────────────────────────────────────────────

# Scaffolding a coding CLI leaves behind. Removed as whole directories before the file
# sweep: codex initialises a git repo in its working root even with --skip-git-repo-check,
# and letting the allowlist delete a .git tree file-by-file means hundreds of entries in the
# removed-list for something that was never a candidate artifact.
_TOOL_DIRS = {".git", ".agents", ".codex", ".grok", "__pycache__", "node_modules", ".venv"}


def _prune_tool_dirs(folder: Path) -> list[str]:
    removed: list[str] = []
    for child in folder.iterdir():
        if child.is_dir() and child.name in _TOOL_DIRS:
            shutil.rmtree(child, ignore_errors=True)
            removed.append(f"{child.name}/")
    return removed


def _sweep(folder: Path) -> list[str]:
    """Enforce the artifact-type allowlist + size cap; delete + report anything outside it."""
    removed: list[str] = _prune_tool_dirs(folder)
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
    """Store files created or resized during the run — a worker corrupting pipeline state.

    Size (not mtime) is the signal for an existing path: concurrent rails and scanners bump
    mtimes without rewriting bytes, and that used to false-positive the tripwire into discarding
    real charts. A new path, or a path whose byte length changed, still fails loudly.
    """
    escaped: list[str] = []
    for path, (_mtime_ns, size) in after.items():
        prior = before.get(path)
        if prior is None or prior[1] != size:
            escaped.append(path)
    return sorted(escaped)


def _pct_supported_by_corpus(token: str, corpus: str) -> bool:
    """True when ``token`` is literally in evidence, or is a ratio of two corpus numbers.

    Charts often derive ``60k / 85k → 71%``; requiring the percentage string itself in a claim
    rejects honest arithmetic. Invented percentages that match no pair still fail.
    """
    if token in corpus:
        return True
    bare = token.rstrip("%")
    try:
        target = float(bare)
    except ValueError:
        return False
    # "71 percent" / "71 pct" without a % sign in the claim text
    if re.search(rf"(?<!\d){re.escape(bare)}\s*(?:%|percent|pct)\b", corpus, re.I):
        return True
    # Comma-grouped counts ("60,000") must parse as single magnitudes for ratio checks.
    nums = [float(x) for x in _CORPUS_NUM.findall(corpus.replace(",", ""))]
    for i, a in enumerate(nums):
        if a == 0:
            continue
        for b in nums[i + 1 :]:
            if b == 0:
                continue
            for num, den in ((a, b), (b, a)):
                ratio = 100.0 * num / den
                if abs(ratio - target) <= max(0.75, 0.02 * abs(target)):
                    return True
    return _arithmetic_supported(target, nums)


def _arithmetic_supported(target: float, nums: list[float]) -> bool:
    """Is ``target`` a plain sum or difference of two cited numbers?

    The case that killed a real figure: the claims held South Korea's total exports
    ($496.3bn) and its chip exports ($149bn), and the chart plotted chips against the
    NON-chip remainder — 496.3 - 149 = 347.3. That is the whole point of a
    part-of-whole split, and it was rejected because 347.3 appears in no claim.
    Demanding that every plotted value be quoted verbatim forbids arithmetic, which
    means forbidding most honest charts.

    Deliberately shallow: two operands, add or subtract. A number that matches no pair
    is still unverified, so an invented figure fails exactly as before.
    """
    tol = max(0.05, 0.005 * abs(target))
    for i, a in enumerate(nums):
        for b in nums[i + 1:]:
            if abs((a - b) - target) <= tol or abs((b - a) - target) <= tol:
                return True
            if abs((a + b) - target) <= tol:
                return True
    return False


#: How many sourced rows become claims. A figure's series can be long; the ledger wants the
#: shape of the evidence, not a transcription of the CSV, which is published beside it anyway.
_MAX_SOURCED_CLAIMS = 12

#: Provenance the WORKER wrote into its own caption. The harness owns provenance — it stamps the
#: AI label, the publishers and the as-of itself — so a worker that also writes them produces a
#: caption carrying every line twice. Observed under one map: a bare URL for each of eight plotted
#: points, then "As of <date>" and a Source list, then the harness's own label, Source list and
#: as-of again. ~1,400 characters, the largest block of text on the page, and nothing a reader
#: wants to read. The full per-row attribution already ships in the figure's data.csv and the
#: article's receipts, which is where an inspectable audit trail belongs; the caption's job is to
#: say what the figure shows.
_WORKER_PROVENANCE = re.compile(
    r"(?:\*\*)?(?:Sources?|Data source|Basemap|Geocodes?)(?:\*\*)?\s*:.*$"
    r"|\bAs of \d{4}-\d{2}-\d{2}\.?"
    r"|\(?https?://\S+\)?",
    re.IGNORECASE | re.DOTALL,
)


#: Labels left standing when their URL is removed. Stripping the link out of
#: "WeatherNext confidence: https://…" leaves "WeatherNext confidence:" dangling at the end of the
#: caption, which reads as truncation — worse than the duplication being fixed.
_ORPHAN_LABEL = re.compile(r"(?:^|[.;])\s*[^.;:]{0,60}:\s*(?=[.;]|$)")


def _strip_provenance(text: str) -> str:
    """Drop worker-authored source/as-of/URL text so the harness's stamp is the only one."""
    out = _WORKER_PROVENANCE.sub("", text or "")
    out = _ORPHAN_LABEL.sub(".", out)
    out = re.sub(r"\s*([.;])\s*(?=[.;])", "", out)          # collapse punctuation left adjacent
    return re.sub(r"\s*[—,;:]\s*$", "", out.strip())


def _sourced_claims(data_text: str, caption: str, request: AnalyticsRequest) -> list[dict]:
    """Turn a sourced figure's data table into claim-shaped rows for the profile.

    One claim per data row, phrased so it reads as a statement rather than a CSV line, and
    every one carries the publisher URL the sourced-mode provenance check already required.
    Without a URL nothing is emitted: an unattributed number is not a claim.
    """
    url_match = re.search(r"https?://\S+", caption or "")
    if not url_match:
        return []
    url = url_match.group(0).rstrip(").,;")

    rows = [ln.strip() for ln in (data_text or "").splitlines() if ln.strip()]
    if len(rows) < 2:
        return []
    header = [h.strip() for h in rows[0].split(",")]
    subject = (request.title or request.question or "figure data").strip()

    out: list[dict] = []
    for row in rows[1:  _MAX_SOURCED_CLAIMS + 1]:
        cells = [c.strip() for c in row.split(",")]
        if len(cells) != len(header):
            continue
        pairs = ", ".join(f"{h} {c}" for h, c in zip(header, cells) if c)
        if pairs:
            out.append({"text": f"{subject}: {pairs}", "url": url})
    return out


def _visual_unverified_figures(data_text: str, cited_claims: list[Claim], sources_by_id: dict) -> list[str]:
    """Significant numbers in the plotted data that appear NOWHERE in the cited evidence — the
    visual analog of ``unverified_prose_figures``. Same conservative stance (substring, err toward
    missing a drift rather than inventing one). Derived percentages from cited counts are allowed."""
    corpus = " ".join(c.text for c in cited_claims)
    for c in cited_claims:
        for sid in c.supported_by:
            s = sources_by_id.get(sid)
            if s and s.snapshot and s.snapshot.excerpt:
                corpus += " " + s.snapshot.excerpt
    out: list[str] = []
    for n in dict.fromkeys(_SIG_NUM.findall(data_text)):
        if _YEAR_LIKE.match(n):
            continue        # an axis label, not a claim — see _YEAR_LIKE
        if n.endswith("%"):
            if not _pct_supported_by_corpus(n, corpus):
                out.append(n)
        elif n not in corpus and not _pct_supported_by_corpus(n, corpus):
            # Bare values get the same arithmetic leeway percentages already had: a
            # part-of-whole split derives its remainder, and that is not fabrication.
            out.append(n)
    return out


def _timeout_for(request: AnalyticsRequest) -> float:
    if request.kind == "image" or request.may_source:
        return _TIMEOUT_SOURCED_S
    return _TIMEOUT_S


def _collect(folder: Path, kind: str) -> tuple[Path | None, Path | None, str]:
    """Find the produced (visual, data, caption) after the sweep. visual/data may be None (a skip/fail)."""
    visual = next((folder / n for n in _VISUAL_NAMES.get(kind, ()) if (folder / n).exists()), None)
    data = folder / _DATA_NAME if (folder / _DATA_NAME).exists() else None
    cap = (folder / _CAPTION_NAME).read_text(encoding="utf-8").strip() if (folder / _CAPTION_NAME).exists() else ""
    return visual, data, cap


def _caption(
    request: AnalyticsRequest,
    worker_caption: str,
    profile: SignalProfile,
    cited_claims: list[Claim],
    as_of: str,
) -> str:
    """Harness-assembled caption: what it shows + worker detail + human provenance (never claim ids).

    Structure for a cold reader: (1) what is measured / what the figure shows, (2) any worker
    takeaway that adds, (3) source + as-of + AI label. Machine ids stay out of the reader view.
    """
    def _clean(text: str) -> str:
        text = re.sub(r"\b(?:clm_|src_)[0-9a-fA-F]+\b", "", text or "")
        text = _strip_provenance(text)
        return re.sub(r"\s{2,}", " ", text).strip(" —,-")

    shows = _clean(request.question or request.title)
    worker = _clean(worker_caption)
    # Avoid repeating the same sentence twice if the worker paraphrased the question.
    if worker and shows and worker.lower()[:40] == shows.lower()[:40]:
        worker = ""
    if worker and shows and shows.lower() in worker.lower():
        body = worker
    elif worker and shows:
        # Two independent sentences, so punctuate between them. Bare concatenation published
        # "...how much depends on water EU electricity generation in 2025, by source share",
        # which reads as one broken sentence and hides where the summary ends.
        body = f"{shows.rstrip('.')}. {worker}"
    else:
        body = worker or shows or _clean(request.title)

    sources_by_id = {s.id: s for s in profile.source_ledger}
    pubs: list[str] = []
    for c in cited_claims:
        for sid in c.supported_by:
            s = sources_by_id.get(sid)
            if not s:
                continue
            label = (s.publisher or s.title or "").strip()
            if label and label not in pubs:
                pubs.append(label)
    # For sourced analytics the worker caption should already name the publisher; still stamp
    # the AI label so the figure never passes as a pre-existing official graphic.
    label = AI_ANALYTIC_LABEL_SOURCED if request.may_source and not cited_claims else AI_ANALYTIC_LABEL
    tail = [label + "."]
    if pubs:
        tail.append(f"Source: {', '.join(pubs[:3])}.")
    elif request.may_source and request.source_hint:
        # Soft provenance when profile held no source ledger rows for this figure.
        tail.append(f"Sourced for this figure ({_clean(request.source_hint)[:120]}).")
    if as_of:
        tail.append(f"As of {as_of}.")
    return f"{body} — {' '.join(tail)}".strip()


# ── the runner (injectable so tests never spawn a subprocess) ─────────────────────────────────

def _grok_runner(
    prompt: str, folder: Path, *, timeout: float, allow_web: bool = False,
) -> tuple[bool, str]:
    """Run the configured coding harness headless, cwd pinned to the scratch folder.

    Kept under this name because it is the worker's one subprocess seam and every caller
    already injects around it; *which* CLI runs is now ``analytics_harness``'s decision
    (codex by default, grok when quota allows). ``allow_web`` is True only for may_source
    requests — profile-held charts stay offline.
    """
    return resolve_harness().run(prompt, folder, timeout=timeout, allow_web=allow_web)


Runner = Callable[[str, Path], tuple[bool, str]]


def grok_version() -> str:
    """The exact harness version — stamped onto every artifact as provenance, so a shift in
    analytics quality can be correlated to a tool version from the ledger instead of guessed."""
    return resolve_harness().version()


def update_grok() -> str:
    """Update the harness AT A RUN BOUNDARY (never mid-run — one tool version per article)."""
    return resolve_harness().update()


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
    timeout: float | None = None,
    version: str = "",
) -> AnalyticsArtifact:
    """Build one request into an artifact, with the harness owning integrity end-to-end.

    Accepts profile-grounded requests (``data_refs``) and/or source-at-analytics-time requests
    (``may_source`` + ``source_hint``). The two paths can combine; neither invents numbers.
    """
    workspace = workspace or default_workspace()
    payload, cited_claims, as_of = _grounded_data(request, profile)
    ai_label = (
        AI_ANALYTIC_LABEL_SOURCED
        if request.may_source and not request.data_refs
        else AI_ANALYTIC_LABEL
    )
    result = AnalyticsArtifact(
        request_id=request.id, kind=request.kind, title=request.title,
        question=request.question,
        data_refs=request.data_refs, as_of=as_of, ai_label=ai_label,
        visual_class=request.visual_class, priority=request.priority,
        placement=request.placement, reader_gap=request.reader_gap,
        generator=GENERATOR, model=version or "grok-build",
        generated_at=datetime.now(UTC).isoformat(),
    )

    if not request.data_refs and not (request.may_source and (request.source_hint or request.spec)):
        return result.model_copy(update={
            "status": "failed",
            "note": "no data_refs and not may_source (need profile data or a source hint)",
        })

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
        prompt = _prompt(may_source=bool(request.may_source))
        allow_web = bool(request.may_source)
        run_timeout = _timeout_for(request) if timeout is None else timeout
        ok, tail = (runner or (lambda p, f: _grok_runner(
            p, f, timeout=run_timeout, allow_web=allow_web)))(prompt, folder)

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

        # (3) figure check — profile-held path: numbers must appear in cited evidence.
        # Source-at-time path: non-empty data table PLUS a publisher URL in caption.md.
        # A CSV alone is not provenance — without a URL we refuse to call the figure verified.
        data_text = data.read_text(encoding="utf-8", errors="replace") if data else ""
        sources_by_id = {s.id: s for s in profile.source_ledger}
        # ``may_source`` decides the standard, NOT "may_source and no claims". A request can
        # be both grounded in the profile and permitted to fetch what the profile lacks — that
        # is the normal shape for a trajectory, where the claims hold this year and the series
        # needs the prior decade. Requiring every plotted number to appear in a claim made such
        # a request impossible to satisfy: anything the worker fetched was, by definition, not
        # in the ledger, so a grounded+sourced figure could only ever fail. Provenance is still
        # enforced — a sourced figure must carry its publisher URL — it is the standard that
        # changes, not the rigour.
        if request.may_source:
            rows = [ln for ln in data_text.splitlines() if ln.strip()]
            has_table = len(rows) >= 2  # header + ≥1 data row
            has_url = bool(re.search(r"https?://\S+", worker_cap or "", re.I))
            unverified: list[str] = []
            if not has_table:
                unverified.append("empty or missing sourced data.csv")
            if not has_url:
                unverified.append("caption.md must name the publisher URL for sourced figures")
            figure_check = {
                "checked": True,
                "verified": not unverified,
                "unverified": unverified,
                "mode": "sourced",
            }
            note = (
                "" if figure_check["verified"]
                else "sourced analytic failed provenance check: " + ", ".join(unverified)
            )
        else:
            unverified = (
                _visual_unverified_figures(data_text, cited_claims, sources_by_id)
                if data_text else []
            )
            figure_check = {
                "checked": bool(data_text),
                "verified": data_text != "" and not unverified,
                "unverified": unverified,
                "mode": "profile",
            }
            note = (
                ("figure check: numbers not found in cited evidence — " + ", ".join(unverified))
                if unverified else ""
            )

        # (3b) geometry check — is the picture LEGIBLE, not just honest? Every other gate here
        # asks whether the numbers are true; none asked whether the labels survive to the edge of
        # the frame, and a timeline shipped with its right-hand text running off the canvas.
        # Decidable from the file, invisible to the worker (matplotlib reports success), and fatal
        # to the one thing a label is for — so it is checked, not requested.
        if visual.suffix == ".svg":
            from .analytics_geometry import check_fit

            misfit = check_fit(visual.read_text(encoding="utf-8", errors="replace"))
            if misfit:
                return _finalize(result, status="failed", swept=removed,
                                 note=f"figure does not fit its canvas: {misfit}")

        # Data the worker went and fetched is EVIDENCE, not scratch. Carry it back so it can
        # enter the claim ledger instead of dying with the scratch folder — the numbers under
        # a published figure should be as inspectable as any other claim.
        if request.may_source and figure_check.get("verified"):
            result = result.model_copy(update={
                "sourced_claims": _sourced_claims(data_text, worker_cap, request),
            })

        # Failed integrity is not a shippable figure — do not copy into the reader path.
        if not figure_check.get("verified"):
            return _finalize(
                result, status="integrity_check_failed", swept=removed,
                figure_check=figure_check,
                note=note or "figure integrity check failed",
            )

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
            caption=_caption(request, worker_cap, profile, cited_claims, as_of),
            figure_check=figure_check,
            note=note,
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
        def _skip_all(reason: str) -> dict[str, Any]:
            skipped = [
                {
                    **r.model_dump(),
                    "request_id": r.id,
                    "status": "skipped",
                    "note": reason,
                }
                for r in plan.requests
            ]
            context.emit(ANALYTICS_WORKER_COMPLETED, {
                "produced": 0, "total": len(skipped), "note": reason,
            })
            return {"analytics_artifacts": skipped}

        stack_ok, stack_note = workspace_stack_ready()
        if not stack_ok:
            return _skip_all(stack_note)

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
                return _skip_all(f"analytics canary failed: {canary_note} (version {version})")

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
