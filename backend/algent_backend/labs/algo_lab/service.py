"""
High-level service facade for Algo Lab functionality.
"""
from __future__ import annotations

from dataclasses import asdict
from typing import Any, Dict

from .experiments import (
    ExperimentResult,
    SortingExperimentConfig,
    run_experiment,
)
from .datasets import SequenceSpec


class AlgoLabService:
    """Facade coordinating experiment planning/execution."""

    def run_sorting(self, payload: Dict[str, Any]) -> ExperimentResult:
        dataset_cfg = payload.get("dataset") or {}
        if isinstance(dataset_cfg, SequenceSpec):
            dataset_spec = dataset_cfg
        else:
            dataset_spec = SequenceSpec(**dataset_cfg)
        cfg = SortingExperimentConfig(
            name=payload.get("name", "adhoc-sorting"),
            algorithm=payload["algorithm"],
            dataset=dataset_spec,
            metrics=payload.get("metrics") or SortingExperimentConfig().metrics,
            collect_trace=payload.get("collect_trace", False),
            options=payload.get("options", {}),
        )
        return run_experiment(cfg)

    def quickstart(self) -> dict:
        """Convenience helper for smoke tests."""
        result = run_experiment(
            SortingExperimentConfig(
                name="quickstart",
                algorithm="merge_sort",
            )
        )
        return result.summary()
