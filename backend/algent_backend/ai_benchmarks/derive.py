"""
Derived series — what the charts and the desk read. Pure functions of the stored results; nothing here names a model, a lab or a benchmark.

* ``frontier``    — the best MEASURED score so far, as the list of results that each set a new record (a step line over time).
* open vs closed  — the frontier of open-weights models against the frontier of closed ones, and how far in TIME the open one trails.
* per lab         — each lab's own frontier (its best to date), for the labs with the highest scores.
* saturation      — the best score as a share of the benchmark's ceiling (None for open-ended scales such as Elo).
* velocity        — how far the frontier moved in the last year.

Higher scores are better on every benchmark kept (bounded fractions, Elo, index points, minutes). Self-reported scores are listed
beside the measured ones and NEVER enter a frontier, an open/closed comparison or a saturation.
"""

from __future__ import annotations

from datetime import date, timedelta
from typing import Any

from . import flags
from .contracts import Benchmark, Result


def _d(text: str) -> date:
    return date.fromisoformat(text[:10])


def frontier(results: list[Result]) -> list[Result]:
    """The results that each beat every earlier one, oldest first (ties go to the first to reach the score)."""
    best, out = None, []
    for r in sorted(results, key=lambda r: (r.date, -r.score)):
        if best is None or r.score > best:
            best = r.score
            out.append(r)
    return out


def best_per_model(results: list[Result]) -> list[Result]:
    """Each model variant's best score (a variant is the source's own model id)."""
    top: dict[str, Result] = {}
    for r in results:
        if r.model_id not in top or r.score > top[r.model_id].score:
            top[r.model_id] = r
    return list(top.values())


def point(r: Result) -> dict[str, Any]:
    return {"d": r.date, "s": r.score, "m": r.model, "l": r.lab}


def open_lag_days(open_f: list[Result], closed_f: list[Result]) -> int | None:
    """How many days the open-weights frontier trails: the date the closed frontier first reached today's best open score, to the date the
    open model set it. None when either side is empty; 0 or negative when open weights lead or tie."""
    if not open_f or not closed_f:
        return None
    top = open_f[-1]
    reached = next((c for c in closed_f if c.score >= top.score), None)
    return (_d(top.date) - _d(reached.date)).days if reached else None


def view(b: Benchmark, results: list[Result], *, as_of: date) -> dict[str, Any] | None:
    """One benchmark's published view, or None when there is nothing measured or claimed for it."""
    horizon = as_of.isoformat()
    mine = [r for r in results if r.benchmark == b.id and r.date <= horizon]
    measured = [r for r in mine if r.verification == "measured"]
    claimed = sorted((r for r in mine if r.verification == "self_reported"), key=lambda r: r.date, reverse=True)
    if not measured and not claimed:
        return None
    models = best_per_model(measured)
    out: dict[str, Any] = {
        "id": b.id, "name": b.name, "source": b.source, "source_url": b.source_url, "unit": b.unit, "ceiling": b.ceiling, "baseline": b.baseline,
        "released": b.released, "superseded_by": b.superseded_by, "n_models": len(models), "n_results": len(measured),
        "as_of": max((r.date for r in measured), default=""), "observed": max((r.observed_on for r in measured), default=""),
    }
    chart = len(models) >= flags.MIN_MODELS_FOR_FRONTIER
    fr = frontier(measured) if chart else []
    out["frontier"] = [point(r) for r in fr]
    best = fr[-1] if fr else (max(measured, key=lambda r: r.score) if measured else None)
    out["best"] = point(best) | {"weights": best.weights} if best else None
    out["saturation"] = round(best.score / b.ceiling, 4) if best and b.ceiling else None
    prior = [r for r in measured if r.date <= (as_of - timedelta(days=flags.RECENT_DAYS)).isoformat()]
    out["velocity"] = round(best.score - max(r.score for r in prior), 6) if best and prior else None
    out["new_records"] = [point(r) for r in fr if r.date >= (as_of - timedelta(days=flags.NEW_RECORD_DAYS)).isoformat()][-3:]
    open_f = frontier([r for r in measured if r.weights == "open"]) if chart else []
    closed_f = frontier([r for r in measured if r.weights == "closed"]) if chart else []
    out["open"], out["closed"] = [point(r) for r in open_f], [point(r) for r in closed_f]
    out["open_lag_days"] = open_lag_days(open_f, closed_f)
    out["gap"] = round(closed_f[-1].score - open_f[-1].score, 6) if open_f and closed_f else None
    labs: dict[str, list[Result]] = {}
    for r in measured:
        labs.setdefault(r.lab, []).append(r)
    ranked = sorted(labs, key=lambda k: -max(r.score for r in labs[k]))[:flags.TOP_LABS] if chart else []
    out["labs"] = {k: [point(r) for r in frontier(labs[k])] for k in ranked}
    out["top"] = [point(r) | {"weights": r.weights, "lab_name": r.lab_name}
                  for r in sorted(models, key=lambda r: -r.score)[:flags.TOP_MODELS]]
    out["claimed"] = [point(r) | {"lab_name": r.lab_name, "url": r.url, "weights": r.weights, "observed_on": r.observed_on} for r in claimed[:10]]
    return out


def lab_summary(results: list[Result]) -> list[dict[str, Any]]:
    """Every lab seen, ordered by how many benchmark records it holds (the site's stable colour order falls back on this for unknown labs)."""
    by_lab: dict[str, dict[str, Any]] = {}
    for r in results:
        if r.verification != "measured":
            continue
        row = by_lab.setdefault(r.lab, {"id": r.lab, "name": r.lab_name, "models": set(), "records": 0})
        row["models"].add(r.model_id)
    by_bench: dict[str, list[Result]] = {}
    for r in results:
        if r.verification == "measured":
            by_bench.setdefault(r.benchmark, []).append(r)
    for rs in by_bench.values():
        if len(best_per_model(rs)) >= flags.MIN_MODELS_FOR_FRONTIER:
            for r in frontier(rs):
                by_lab[r.lab]["records"] += 1
    return sorted(({"id": v["id"], "name": v["name"], "models": len(v["models"]), "records": v["records"]} for v in by_lab.values()),
                  key=lambda v: (-v["records"], -v["models"], v["id"]))
