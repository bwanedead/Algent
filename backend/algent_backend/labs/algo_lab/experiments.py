"""
Experiment definitions and orchestration specific to Algo Lab.
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
    """
    return {"status": "planned", "experiment": cfg.name}
