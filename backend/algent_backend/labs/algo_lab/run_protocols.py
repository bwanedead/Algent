"""
Run record protocol helpers for Algo Lab.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass, is_dataclass
from datetime import datetime, timedelta, timezone
import json
from typing import Any, Dict, List

from .experiments import ExperimentResult, SortingExperimentConfig
from .metrics import MetricResult


def canonical_float(value: float) -> str:
    """Normalize floats to a stable ASCII representation."""
    if value == 0.0:
        return "0"
    return format(value, ".10g")


def _normalize_value(value: Any) -> Any:
    if is_dataclass(value):
        return _normalize_value(asdict(value))
    if isinstance(value, dict):
        return {key: _normalize_value(val) for key, val in value.items()}
    if isinstance(value, list):
        return [_normalize_value(item) for item in value]
    if isinstance(value, tuple):
        return [_normalize_value(item) for item in value]
    if isinstance(value, float):
        return canonical_float(value)
    return value


def canonical_json(payload: Any) -> str:
    """Return a deterministic JSON string for meaningful payloads."""
    normalized = _normalize_value(payload)
    return json.dumps(normalized, sort_keys=True, separators=(",", ":"), ensure_ascii=True)


def _utc_iso(dt: datetime) -> str:
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")


@dataclass(frozen=True)
class AlgoExperimentSpec:
    title: str
    algo_name: str
    goal: str | None = None
    notes: str | None = None

    @classmethod
    def from_config(cls, cfg: SortingExperimentConfig) -> "AlgoExperimentSpec":
        return cls(
            title=cfg.name,
            algo_name=cfg.algorithm,
        )

    def to_node_props(self) -> Dict[str, Any]:
        props: Dict[str, Any] = {
            "title": self.title,
            "algo_name": self.algo_name,
        }
        if self.goal:
            props["goal"] = self.goal
        if self.notes:
            props["notes"] = self.notes
        return props


@dataclass(frozen=True)
class AlgoRunConfig:
    title: str
    algo_name: str
    params: str
    seed: int
    status: str
    started_at_utc: str
    ended_at_utc: str
    summary: str | None = None
    error: str | None = None
    step_count: int | None = None

    def to_node_props(self) -> Dict[str, Any]:
        props: Dict[str, Any] = {
            "title": self.title,
            "algo_name": self.algo_name,
            "params": self.params,
            "seed": self.seed,
            "status": self.status,
            "started_at_utc": self.started_at_utc,
            "ended_at_utc": self.ended_at_utc,
        }
        if self.summary:
            props["summary"] = self.summary
        if self.error:
            props["error"] = self.error
        if self.step_count is not None:
            props["step_count"] = self.step_count
        return props


@dataclass(frozen=True)
class MetricsTimeSeries:
    metric_name: str
    points: List[Dict[str, Any]]
    units: str | None = None

    @classmethod
    def from_metric(cls, metric: MetricResult) -> "MetricsTimeSeries":
        points = [{"index": 0, "value": metric.value}]
        return cls(metric_name=metric.name, points=points, units=metric.unit)

    def data_json(self) -> str:
        return canonical_json({"points": self.points})


@dataclass(frozen=True)
class AlgoRunResult:
    experiment: AlgoExperimentSpec
    run: AlgoRunConfig
    metrics: List[MetricsTimeSeries]

    @classmethod
    def from_experiment_result(
        cls,
        result: ExperimentResult,
        *,
        now_utc: datetime | None = None,
    ) -> "AlgoRunResult":
        if now_utc is None:
            now_utc = datetime.now(timezone.utc)
        duration = max(0.0, result.completed_at - result.planned_at)
        started_at = now_utc - timedelta(seconds=duration)
        params_payload = {
            "experiment": result.experiment.name,
            "algorithm": result.experiment.algorithm,
            "dataset": asdict(result.experiment.dataset),
            "metrics": list(result.experiment.metrics),
            "collect_trace": result.experiment.collect_trace,
            "options": dict(result.experiment.options),
        }
        params_json = canonical_json(params_payload)
        seed = result.experiment.dataset.seed
        run_title = f"{result.experiment.algorithm}::{result.experiment.name}"
        run = AlgoRunConfig(
            title=run_title,
            algo_name=result.experiment.algorithm,
            params=params_json,
            seed=seed if seed is not None else 0,
            status="success",
            started_at_utc=_utc_iso(started_at),
            ended_at_utc=_utc_iso(now_utc),
        )
        metrics = [MetricsTimeSeries.from_metric(metric) for metric in result.metrics]
        return cls(
            experiment=AlgoExperimentSpec.from_config(result.experiment),
            run=run,
            metrics=metrics,
        )
