"""Deterministic SYNTHETIC trial set that exercises every rule of the trial contract.

No model or harness was run. Every record is ``dataset_kind: synthetic`` and the report says
so on its first screen. The scenarios are chosen to hit edge cases (rescues, unknown
interventions, budget overruns, unmeasured resources, indeterminate outcomes, a changed task
version), not to suggest any finding.
"""

from __future__ import annotations

import json
from datetime import date, timedelta
from pathlib import Path

from .contracts import TRIAL_SCHEMA
from .report import write_report

DEMO_FILE = "synthetic_trials.jsonl"

_STUDY = "demo-noninterference-frontier"
_PROTOCOL = "demo-protocol-0"
_EVALUATION = {"rubric": "demo-goal-check", "rubric_version": "0", "evaluator": "synthetic-label"}
_PROVENANCE = {
    "source": "ohmega-research-demo",
    "reference": "algent_backend.ohmega_research.demo (generated; no model or harness was run)",
}
_RETRY_POLICY = "retry once after a harness error; resources summed over attempts"

_SYSTEMS = {
    "alpha": {"model": "synthetic-model-alpha", "harness": "synthetic-harness-1",
              "config_version": "cfg-0"},
    "beta": {"model": "synthetic-model-beta", "harness": "synthetic-harness-1",
             "config_version": "cfg-0"},
}
_TASKS = {
    "repair-v1": {"id": "demo-repo-repair", "version": "1", "family": "repo-repair",
                  "demands": {"abstraction": 2, "branching": 1, "recovery": 2}},
    "plan-v1": {"id": "demo-multistep-plan", "version": "1", "family": "multi-step-planning",
                "demands": {"abstraction": 3, "branching": 3, "recovery": 1}},
    "migrate-v1": {"id": "demo-data-migration", "version": "1", "family": "data-migration",
                   "demands": {"abstraction": 2, "branching": 2, "recovery": 2}},
    "migrate-v2": {"id": "demo-data-migration", "version": "2", "family": "data-migration",
                   "demands": {"abstraction": 2, "branching": 2, "recovery": 3}},
}
_COHORT_START = {"2026-07": date(2026, 7, 6), "2026-09": date(2026, 9, 7)}

# scenario -> (outcome, terminal reason, intervention, cost as a fraction of the limit
# with None = not measured, attempts used)
_SCENARIOS = {
    "clean": ("success", "completed", "observed_none", 0.5, 1),
    "rescued": ("success", "completed", "observed_present", 0.6, 1),
    "unlogged": ("success", "completed", "unknown", 0.4, 1),
    "gave_up": ("failure", "gave_up", "observed_none", 0.7, 1),
    "timeout": ("failure", "timeout", "observed_none", 0.8, 1),
    "exhausted": ("failure", "budget_exhausted", "observed_none", 1.0, 1),
    "overrun": ("success", "completed", "observed_none", 1.3, 1),
    "judge_failed": ("indeterminate", "evaluator_error", "observed_none", 0.5, 1),
    "unmetered": ("success", "completed", "observed_none", None, 1),
    "retried": ("success", "completed", "observed_none", 0.9, 2),
}
_EARLY = ("clean", "gave_up", "rescued", "unlogged", "timeout", "clean", "unmetered",
          "judge_failed")
_LATE = ("clean", "clean", "rescued", "overrun", "exhausted", "retried", "gave_up", "clean")

# (system, task, cohort, assigned cost limit in USD, scenario plan)
_CELLS = (
    ("alpha", "repair-v1", "2026-07", 2.0, _EARLY),
    ("alpha", "repair-v1", "2026-09", 2.0, _LATE),
    ("alpha", "repair-v1", "2026-07", 5.0, _EARLY),
    ("alpha", "repair-v1", "2026-09", 5.0, _LATE),
    ("alpha", "plan-v1", "2026-07", 5.0, _EARLY),
    ("alpha", "plan-v1", "2026-09", 5.0, _LATE),
    ("alpha", "migrate-v1", "2026-07", 5.0, _EARLY),
    ("alpha", "migrate-v2", "2026-09", 5.0, _LATE),
    ("beta", "repair-v1", "2026-09", 5.0, _LATE),
)


def demo_records() -> list[dict]:
    return [
        _record(system, task, cohort, limit, index, scenario)
        for system, task, cohort, limit, plan in _CELLS
        for index, scenario in enumerate(plan)
    ]


def write_demo(output_dir: Path) -> dict[str, Path]:
    """Write the synthetic JSONL and its report into ``output_dir``."""
    output_dir.mkdir(parents=True, exist_ok=True)
    trials_path = output_dir / DEMO_FILE
    lines = "".join(json.dumps(r, sort_keys=True) + "\n" for r in demo_records())
    trials_path.write_text(lines, encoding="utf-8", newline="\n")
    return {"trials": trials_path, **write_report(trials_path, output_dir)}


def _record(system: str, task: str, cohort: str, limit: float, index: int,
            scenario: str) -> dict:
    outcome, terminal, intervention, cost_fraction, attempts = _SCENARIOS[scenario]
    return {
        "schema": TRIAL_SCHEMA,
        "trial_id": f"demo-{cohort}-{system}-{task}-usd{limit:g}-{index:02d}",
        "study_id": _STUDY,
        "protocol_version": _PROTOCOL,
        "dataset_kind": "synthetic",
        "cohort": cohort,
        "trial_date": (_COHORT_START[cohort] + timedelta(days=index)).isoformat(),
        "task": _TASKS[task],
        "system": _SYSTEMS[system],
        "evaluation": _EVALUATION,
        "provenance": _PROVENANCE,
        "outcome": outcome,
        "terminal_reason": terminal,
        "intervention": _intervention(intervention, scenario),
        "attempts": {"count": attempts, "max_allowed": 2, "retry_policy": _RETRY_POLICY,
                     "resources_scope": "all_attempts"},
        "budget": [{"metric": "cost", "unit": "USD", "limit": limit}],
        "resources_used": _resources(system, limit, cost_fraction, index),
        "notes": f"synthetic scenario: {scenario}",
    }


def _intervention(status: str, scenario: str) -> dict:
    if status == "unknown":
        return {"status": "unknown", "evidence": None}
    return {"status": status,
            "evidence": f"synthetic label for scenario '{scenario}'; no transcript exists"}


def _resources(system: str, limit: float, cost_fraction: float | None, index: int) -> list:
    used = [
        {"metric": "cost", "unit": "USD",
         "value": None if cost_fraction is None else round(limit * cost_fraction, 4)},
        {"metric": "output_tokens", "unit": "tokens",
         "value": None if index % 3 == 2 else 1500 + 250 * index},
        {"metric": "wall_time", "unit": "seconds", "value": 120.0 + 30 * index},
        {"metric": "flops", "unit": "FLOP", "value": None},
    ]
    if system == "alpha":  # the beta harness does not report input tokens at all
        used.append({"metric": "input_tokens", "unit": "tokens", "value": 20000 + 1000 * index})
    return used
