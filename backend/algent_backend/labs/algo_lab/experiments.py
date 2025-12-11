"""
Experiment definitions and orchestration specific to Algo Lab.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List
import time

from . import algorithms, metrics
from .algorithms.sorting import SortingOptions, SortingResult
from .datasets import SequenceBatch, SequenceSpec, generate_sequence
from .metrics import MetricResult


@dataclass
class SortingExperimentConfig:
    """Configuration for a sorting experiment."""

    name: str
    algorithm: str
    dataset: SequenceSpec = field(default_factory=SequenceSpec)
    metrics: List[str] = field(
        default_factory=lambda: ["latency_ms", "comparisons", "is_sorted"]
    )
    collect_trace: bool = False
    options: Dict[str, Any] = field(default_factory=dict)


@dataclass
class ExperimentPlan:
    experiment: SortingExperimentConfig
    dataset: SequenceSpec
    algorithm_available: bool


@dataclass
class ExperimentResult:
    experiment: SortingExperimentConfig
    dataset: SequenceBatch
    outcome: SortingResult
    metrics: List[MetricResult]
    planned_at: float
    completed_at: float

    def summary(self) -> dict:
        return {
            "experiment": self.experiment.name,
            "algorithm": self.experiment.algorithm,
            "metrics": [metric.__dict__ for metric in self.metrics],
            "duration_ms": round(self.completed_at - self.planned_at, 3),
            "dataset": self.dataset.summary(),
        }


def plan_experiment(cfg: SortingExperimentConfig) -> ExperimentPlan:
    descriptor = [alg for alg in algorithms.list_available("sorting") if alg.name == cfg.algorithm]
    return ExperimentPlan(
        experiment=cfg,
        dataset=cfg.dataset,
        algorithm_available=bool(descriptor),
    )


def run_experiment(cfg: SortingExperimentConfig) -> ExperimentResult:
    plan = plan_experiment(cfg)
    if not plan.algorithm_available:
        raise ValueError(f"Algorithm '{cfg.algorithm}' is not registered.")
    planned_at = time.perf_counter()
    batch = generate_sequence(cfg.dataset)
    result = algorithms.run(
        name=cfg.algorithm,
        data=batch.values,
        options=SortingOptions(
            collect_trace=cfg.collect_trace,
            trace_limit=cfg.options.get("trace_limit", 1000),
        ),
    )
    metric_payload = metrics.compute_metrics(result, batch, cfg.metrics)
    completed_at = time.perf_counter()
    return ExperimentResult(
        experiment=cfg,
        dataset=batch,
        outcome=result,
        metrics=metric_payload,
        planned_at=planned_at,
        completed_at=completed_at,
    )
