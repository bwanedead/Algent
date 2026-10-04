"""Descriptive analysis of validated trial records.

Nothing here estimates a growth rate. It counts under a stated denominator policy, inside
cells whose members are genuinely comparable, and says plainly when a comparison across time
is not identifiable. Observed and synthetic records are analysed in separate partitions.
"""

from __future__ import annotations

import hashlib
import json
import math
import statistics
from collections import Counter, defaultdict
from collections.abc import Callable, Iterable, Sequence
from itertools import pairwise

from .contracts import DATASET_KINDS, INTERVENTION_STATUSES, OUTCOMES, TRIAL_SCHEMA, TrialRecord

ANALYSIS_SCHEMA = "ohmega.research.analysis/1"
Z_95 = 1.959963984540054
BUDGET_STATUSES = ("within", "violated", "unverified", "unbudgeted")
SMALL_N = 10

METHODOLOGY = {
    "credited_success": (
        "outcome=success AND intervention=observed_none AND the assigned budget was respected "
        "(or none was assigned). Helped (rescued) successes, unknown-intervention successes and "
        "over-budget successes are never credited."
    ),
    "all_outcomes_rate": (
        "Conservative credited operational yield: credited / every terminal trial. Failures, "
        "timeouts, budget exhaustion, system errors, unknown-intervention trials and "
        "indeterminate trials (including evaluator and environment outages outside the tested "
        "system) all stay in this denominator. It describes what the whole operation delivered; "
        "it is not an estimate of the system's capability where outcomes were unobservable."
    ),
    "confirmed_rate": (
        "Confirmed capability rate: credited / trials whose credit status was ascertained, "
        "meaning intervention observed (none or present), goal outcome observed (success or "
        "failure; outages outside the tested system are indeterminate), and budget compliance "
        "measured. Membership requires ascertainment; it never selects on success versus "
        "failure. Always read it with its coverage."
    ),
    "interval": (
        "95% Wilson score interval, descriptive only. It assumes independent trials; repeated "
        "trials on one task are clustered, so it is not evidence of population-level reliability."
    ),
    "grouping": (
        "A cell matches study, protocol, evaluator rubric/version, exact system (model + harness "
        "+ config version), task id/version (with its fixed family and demand vector), assigned "
        "budget (exact limits), declared attempt policy (max allowed, retry policy, resource "
        "scope) and cohort. Attempts actually used are an outcome, not a key. Observed and "
        "synthetic records are separate partitions, never pooled."
    ),
    "temporal": (
        "Cohorts are compared only inside a series matching every cell field except cohort, "
        "with non-overlapping cohort dates. Differences are descriptive; no trend, "
        "interpolation or extrapolation is computed."
    ),
    "resources": (
        "Each metric/unit is summarised separately with its coverage. Unreported values are "
        "unknown, never zero; metrics are never converted into one another. Grouping uses the "
        "budget assigned before the trial; no frontier is fit to consumption."
    ),
    "goal_distance": (
        "Task difficulty is the prespecified demand vector of the task version, not human "
        "completion time or action count."
    ),
}


def wilson_interval(k: int, n: int, z: float = Z_95) -> tuple[float, float] | None:
    """Wilson score interval for ``k`` successes in ``n`` trials; None when ``n`` is 0."""
    if n < 0 or not 0 <= k <= n:
        raise ValueError(f"need 0 <= k <= n, got k={k}, n={n}")
    if n == 0:
        return None
    p = k / n
    z2 = z * z
    denominator = 1 + z2 / n
    centre = (p + z2 / (2 * n)) / denominator
    half = z * math.sqrt(p * (1 - p) / n + z2 / (4 * n * n)) / denominator
    low = 0.0 if k == 0 else max(0.0, centre - half)
    high = 1.0 if k == n else min(1.0, centre + half)
    return low, high


def budget_status(record: TrialRecord) -> str:
    if not record.budget:
        return "unbudgeted"
    used = {o.metric: o.value for o in record.resources_used}
    values = [used.get(limit.metric) for limit in record.budget]
    if any(v is not None and v > b.limit for v, b in zip(values, record.budget, strict=True)):
        return "violated"
    if any(v is None for v in values):
        return "unverified"
    return "within"


def is_credited(record: TrialRecord) -> bool:
    """Zero-interference, budget-conditioned success: the only success credited to the system."""
    return (
        record.outcome == "success"
        and record.intervention.status == "observed_none"
        and budget_status(record) in ("within", "unbudgeted")
    )


def is_confirmed(record: TrialRecord) -> bool:
    """Whether the record's credit status was ascertained (never a selection on success)."""
    return (
        record.intervention.status != "unknown"
        and record.outcome != "indeterminate"
        and budget_status(record) != "unverified"
    )


def summarize(records: Sequence[TrialRecord]) -> dict:
    n = len(records)
    credited = sum(1 for r in records if is_credited(r))
    confirmed = sum(1 for r in records if is_confirmed(r))
    return {
        "n": n,
        "credited_success": credited,
        "all_outcomes": _rate(credited, n),
        "confirmed": {**_rate(credited, confirmed), "coverage": _ratio(confirmed, n)},
        **_tallies(records),
        "terminal_reasons": dict(sorted(Counter(r.terminal_reason for r in records).items())),
        "helped_success": sum(
            1 for r in records
            if r.outcome == "success" and r.intervention.status == "observed_present"
        ),
        "attempts": {
            "total": sum(r.attempts.count for r in records),
            "max_per_trial": max((r.attempts.count for r in records), default=0),
            "retry_policies": sorted({r.attempts.retry_policy for r in records}),
        },
        "resources": _resources(records),
        "clustering": _clustering(records),
    }


def build_analysis(records: Sequence[TrialRecord], *, input_name: str, input_sha256: str) -> dict:
    by_kind = _group(records, lambda r: r.dataset_kind)
    return {
        "schema": ANALYSIS_SCHEMA,
        "trial_schema": TRIAL_SCHEMA,
        "input": {"name": input_name, "sha256": input_sha256, "records": len(records)},
        "contains_synthetic": "synthetic" in by_kind,
        "mixed_dataset_kinds": len(by_kind) > 1,
        "methodology": METHODOLOGY,
        "provenance": _provenance(records),
        "partitions": [_partition(kind, by_kind[kind]) for kind in DATASET_KINDS if kind in by_kind],
    }


def _ratio(part: int, whole: int) -> float | None:
    return round(part / whole, 6) if whole else None


def _rate(k: int, n: int) -> dict:
    interval = wilson_interval(k, n)
    return {
        "k": k,
        "n": n,
        "rate": _ratio(k, n),
        "wilson95": None if interval is None else [round(interval[0], 6), round(interval[1], 6)],
    }


def _tally(values: Iterable[str], categories: tuple[str, ...]) -> dict[str, int]:
    counts = Counter(values)
    return {category: counts.get(category, 0) for category in categories}


def _tallies(records: Sequence[TrialRecord]) -> dict[str, dict[str, int]]:
    return {
        "outcomes": _tally((r.outcome for r in records), OUTCOMES),
        "intervention": _tally((r.intervention.status for r in records), INTERVENTION_STATUSES),
        "budget": _tally((budget_status(r) for r in records), BUDGET_STATUSES),
    }


def _group(records: Iterable[TrialRecord], key: Callable[[TrialRecord], str]) -> dict:
    groups: dict[str, list[TrialRecord]] = defaultdict(list)
    for record in records:
        groups[key(record)].append(record)
    return groups


def _resources(records: Sequence[TrialRecord]) -> list[dict]:
    reported = [{(o.metric, o.unit): o.value for o in r.resources_used} for r in records]
    keys = {key for row in reported for key in row}
    keys |= {(b.metric, b.unit) for r in records for b in r.budget}
    summaries = []
    for metric, unit in sorted(keys):
        present = [row[(metric, unit)] for row in reported if (metric, unit) in row]
        observed = [value for value in present if value is not None]
        summaries.append({
            "metric": metric,
            "unit": unit,
            "observed": len(observed),
            "reported_unknown": len(present) - len(observed),
            "not_reported": len(records) - len(present),
            "coverage": _ratio(len(observed), len(records)),
            "min": min(observed) if observed else None,
            "median": statistics.median(observed) if observed else None,
            "max": max(observed) if observed else None,
        })
    return summaries


def _clustering(records: Sequence[TrialRecord]) -> dict:
    per_task = Counter((r.task.id, r.task.version) for r in records)
    return {"distinct_tasks": len(per_task), "max_trials_per_task": max(per_task.values(), default=0)}


def _exact_number(value: float) -> str:
    return str(int(value)) if value.is_integer() else repr(value)


def _budget_label(record: TrialRecord) -> str:
    """Human-facing only; identity uses the structured exact values in ``_series_fields``."""
    if not record.budget:
        return "unbudgeted"
    return "; ".join(f"{b.metric} <= {_exact_number(b.limit)} {b.unit}" for b in record.budget)


_SERIES_KEYS = ("study_id", "protocol_version", "evaluation", "system", "task", "budget",
                "attempt_policy")


def _series_fields(record: TrialRecord) -> dict:
    """Everything a cohort comparison must hold fixed (the keys of ``_SERIES_KEYS``)."""
    return {
        "study_id": record.study_id,
        "protocol_version": record.protocol_version,
        "evaluation": {
            "rubric": record.evaluation.rubric,
            "rubric_version": record.evaluation.rubric_version,
            "evaluator": record.evaluation.evaluator,
        },
        "system": {
            "model": record.system.model,
            "harness": record.system.harness,
            "config_version": record.system.config_version,
        },
        "task": {
            "id": record.task.id,
            "version": record.task.version,
            "family": record.task.family,
            "demands": dict(record.task.demands),
        },
        "budget": [{"metric": b.metric, "unit": b.unit, "limit": b.limit} for b in record.budget],
        # The declared policy is a condition; the attempts actually used are an outcome.
        "attempt_policy": {
            "max_allowed": record.attempts.max_allowed,
            "retry_policy": record.attempts.retry_policy,
            "resources_scope": record.attempts.resources_scope,
        },
    }


def _stable_id(prefix: str, fields: dict) -> str:
    digest = hashlib.sha256(json.dumps(fields, sort_keys=True).encode("utf-8")).hexdigest()
    return f"{prefix}-{digest[:10]}"


def _dates(records: Sequence[TrialRecord]) -> list[str]:
    days = [r.trial_date for r in records]
    return [min(days).isoformat(), max(days).isoformat()]


def _display_order(item: dict) -> tuple:
    system = item["system"]
    return (
        system["model"], system["harness"], system["config_version"],
        item["task"].get("id", ""), item["task"].get("version", ""),
        json.dumps(item["budget"], sort_keys=True),
        json.dumps(item["attempt_policy"], sort_keys=True),
        item.get("dates", [""])[0], item.get("cohort", ""),
    )


def _cells(records: Sequence[TrialRecord]) -> list[dict]:
    groups = _group(
        records, lambda r: json.dumps({**_series_fields(r), "cohort": r.cohort}, sort_keys=True)
    )
    cells = []
    for members in groups.values():
        series = _series_fields(members[0])
        cohort = members[0].cohort
        cells.append({
            "cell_id": _stable_id("cell", {**series, "cohort": cohort}),
            "series_id": _stable_id("series", series),
            **series,
            "budget_label": _budget_label(members[0]),
            "cohort": cohort,
            "dates": _dates(members),
            "summary": summarize(members),
        })
    return sorted(cells, key=_display_order)


def _temporal(cells: list[dict]) -> list[dict]:
    by_series: dict[str, list[dict]] = defaultdict(list)
    for cell in cells:
        by_series[cell["series_id"]].append(cell)
    series = []
    for series_id, members in by_series.items():
        members.sort(key=lambda c: (c["dates"][0], c["cohort"]))
        points = [
            {
                "cohort": c["cohort"],
                "cell_id": c["cell_id"],
                "dates": c["dates"],
                "all_outcomes": c["summary"]["all_outcomes"],
                "confirmed": c["summary"]["confirmed"],
            }
            for c in members
        ]
        fixed = {k: members[0][k] for k in (*_SERIES_KEYS, "budget_label")}
        series.append({"series_id": series_id, **fixed, "points": points,
                       **_comparability(points)})
    return sorted(series, key=_display_order)


def _comparability(points: list[dict]) -> dict:
    if len(points) < 2:
        return {"status": "not_estimable",
                "statement": "Single cohort: growth not estimable.", "changes": []}
    if any(a["dates"][1] >= b["dates"][0] for a, b in pairwise(points)):
        return {"status": "not_estimable",
                "statement": "Cohort dates overlap, so their order is not identifiable: "
                             "growth not estimable.",
                "changes": []}
    return {
        "status": "matched_descriptive",
        "statement": f"{len(points)} matched cohorts: descriptive comparison only; "
                     "no trend fitted, nothing interpolated or extrapolated.",
        "changes": [_change(a, b) for a, b in pairwise(points)],
    }


def _delta(a: float | None, b: float | None) -> float | None:
    return None if a is None or b is None else round(b - a, 6)


def _change(a: dict, b: dict) -> dict:
    ia, ib = a["confirmed"]["wilson95"], b["confirmed"]["wilson95"]
    return {
        "from": a["cohort"],
        "to": b["cohort"],
        "confirmed_rate_delta": _delta(a["confirmed"]["rate"], b["confirmed"]["rate"]),
        "all_outcomes_rate_delta": _delta(a["all_outcomes"]["rate"], b["all_outcomes"]["rate"]),
        "confirmed_intervals_overlap": (
            None if not ia or not ib else (ia[0] <= ib[1] and ib[0] <= ia[1])
        ),
    }


_SERIES_AXES: tuple[tuple[str, Callable[[dict], object]], ...] = (
    ("task.version", lambda c: c["task"]["version"]),
    ("protocol_version", lambda c: c["protocol_version"]),
    ("evaluation", lambda c: c["evaluation"]),
    ("budget", lambda c: c["budget"]),
    ("attempt_policy", lambda c: c["attempt_policy"]),
)


def _unpooled(cells: list[dict]) -> list[dict]:
    """Same study, system and task id, but split into several series: say why, never pool."""
    groups: dict[str, dict[str, list[dict]]] = defaultdict(lambda: defaultdict(list))
    for cell in cells:
        key = json.dumps([cell["study_id"], cell["system"], cell["task"]["id"]], sort_keys=True)
        groups[key][cell["series_id"]].append(cell)
    found = []
    for by_series in groups.values():
        if len(by_series) < 2:
            continue
        heads = [members[0] for members in by_series.values()]
        differing = [
            name for name, get in _SERIES_AXES
            if len({json.dumps(get(c), sort_keys=True) for c in heads}) > 1
        ]
        found.append({
            "study_id": heads[0]["study_id"],
            "system": heads[0]["system"],
            "task_id": heads[0]["task"]["id"],
            "differing": differing,
            "series": [
                {
                    "series_id": members[0]["series_id"],
                    "task_version": members[0]["task"]["version"],
                    "protocol_version": members[0]["protocol_version"],
                    "evaluation": members[0]["evaluation"],
                    "budget": members[0]["budget"],
                    "budget_label": members[0]["budget_label"],
                    "attempt_policy": members[0]["attempt_policy"],
                    "cohorts": [c["cohort"] for c in members],
                }
                for members in by_series.values()
            ],
            "statement": f"Kept as {len(by_series)} separate series because "
                         f"{', '.join(differing)} differ; no line is drawn across them.",
        })
    return sorted(found, key=lambda u: (json.dumps(u["system"], sort_keys=True), u["task_id"]))


def _family_rollups(records: Sequence[TrialRecord]) -> list[dict]:
    """Descriptive pools of tasks sharing a family and demand vector; the task mix is shown."""
    def key(record: TrialRecord) -> str:
        fields = _series_fields(record)
        fields["task"] = {"family": record.task.family, "demands": dict(record.task.demands)}
        return json.dumps({**fields, "cohort": record.cohort}, sort_keys=True)

    rollups = []
    for group_key, members in _group(records, key).items():
        fields = json.loads(group_key)
        mix = Counter((r.task.id, r.task.version) for r in members)
        rollups.append({
            **fields,
            "budget_label": _budget_label(members[0]),
            "dates": _dates(members),
            "task_mix": [{"id": i, "version": v, "n": n} for (i, v), n in sorted(mix.items())],
            "summary": summarize(members),
        })
    return sorted(rollups, key=lambda r: (r["task"]["family"], _display_order(r)))


def _inventory(records: Sequence[TrialRecord]) -> dict:
    """Counts only: a rate pooled across a whole partition would mix incomparable cells."""
    confirmed = sum(1 for r in records if is_confirmed(r))
    return {
        "n": len(records),
        "studies": sorted({r.study_id for r in records}),
        "systems": len({(r.system.model, r.system.harness, r.system.config_version)
                        for r in records}),
        "tasks": len({(r.task.id, r.task.version) for r in records}),
        "cohorts": sorted({r.cohort for r in records}),
        **_tallies(records),
        "confirmed_coverage": _ratio(confirmed, len(records)),
    }


def _partition(kind: str, records: Sequence[TrialRecord]) -> dict:
    cells = _cells(records)
    series = _temporal(cells)
    inventory = _inventory(records)
    matched = sum(1 for s in series if s["status"] == "matched_descriptive")
    if matched:
        statement = (f"{matched} of {len(series)} series span two or more matched cohorts; "
                     "the differences are descriptive, not a growth estimate.")
    else:
        statement = "Growth not estimable: no matched series spans two ordered cohorts."
    return {
        "dataset_kind": kind,
        "inventory": inventory,
        "temporal_statement": statement,
        "matched_series": matched,
        "warnings": _warnings(kind, inventory, cells),
        "cells": cells,
        "series": series,
        "unpooled": _unpooled(cells),
        "family_rollups": _family_rollups(records),
    }


def _warnings(kind: str, inventory: dict, cells: list[dict]) -> list[str]:
    n = inventory["n"]
    unknown = inventory["intervention"]["unknown"]
    unverified = inventory["budget"]["unverified"]
    violated = inventory["budget"]["violated"]
    indeterminate = inventory["outcomes"]["indeterminate"]
    small = sum(1 for c in cells if c["summary"]["confirmed"]["n"] < SMALL_N)
    candidates = [
        (kind == "synthetic",
         "SYNTHETIC data: generated to exercise the pipeline; it supports no conclusion about "
         "any real model or harness."),
        (unknown, f"{unknown} of {n} trials have unknown intervention status: they count against "
                  "the operational yield and are outside the confirmed denominator."),
        (unverified, f"{unverified} of {n} trials have unmeasured budgeted resources: budget "
                     "compliance is unverified, so they are outside the confirmed denominator."),
        (violated, f"{violated} of {n} trials exceeded their assigned budget; no success among "
                   "them is credited."),
        (indeterminate, f"{indeterminate} of {n} trials have an unobserved (indeterminate) "
                        "outcome, e.g. an evaluator or environment outage: they lower the "
                        "operational yield and are outside the confirmed denominator."),
        (small, f"{small} of {len(cells)} cells have fewer than {SMALL_N} confirmed trials; "
                "their intervals are wide."),
        (True, "Trials repeated on the same task are clustered; the intervals treat them as "
               "independent and overstate precision for any claim about a task population."),
    ]
    return [message for condition, message in candidates if condition]


def _provenance(records: Sequence[TrialRecord]) -> dict:
    sources = Counter((r.provenance.source, r.provenance.reference, r.dataset_kind)
                      for r in records)
    evaluations = Counter((r.evaluation.rubric, r.evaluation.rubric_version,
                           r.evaluation.evaluator) for r in records)
    protocols = Counter((r.study_id, r.protocol_version) for r in records)
    return {
        "sources": [{"source": s, "reference": ref, "dataset_kind": k, "n": n}
                    for (s, ref, k), n in sorted(sources.items())],
        "evaluations": [{"rubric": r, "rubric_version": v, "evaluator": e, "n": n}
                        for (r, v, e), n in sorted(evaluations.items())],
        "protocols": [{"study_id": s, "protocol_version": p, "n": n}
                      for (s, p), n in sorted(protocols.items())],
        "dates": _dates(records),
    }
