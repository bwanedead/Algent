"""
Experiment definitions and orchestration.

Experiments describe which algorithm to run, with what parameters, and which
metrics to observe. This module should eventually handle scheduling, lifecycle,
and persistence.
"""
from dataclasses import dataclass, field
from typing import Any, Dict, List


@dataclass
class ExperimentConfig:
    """Lightweight representation of an experiment request."""

    name: str
    algorithm: str
    parameters: Dict[str, Any] = field(default_factory=dict)
    metrics: List[str] = field(default_factory=list)


def plan_experiment(cfg: ExperimentConfig) -> dict:
    """
    Placeholder planner that validates requests and returns an execution plan.

    Replace with richer validation and resource allocation.
    """
    # TODO: validate algorithm/metrics existence and produce runnable graph.
    return {"status": "planned", "experiment": cfg.name}

