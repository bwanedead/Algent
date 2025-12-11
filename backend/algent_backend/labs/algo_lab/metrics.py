"""
Metric calculators and aggregators.

Design metrics to be composable so experiments can plug them together. Keep
interfaces thin (e.g., `compute(state) -> MetricResult`).
"""
from __future__ import annotations

from dataclasses import dataclass
import math
from typing import Callable, Dict, Iterable, List

from .algorithms.sorting import SortingResult
from .datasets import SequenceBatch


@dataclass
class MetricResult:
    name: str
    value: float | int | bool
    unit: str | None = None
    details: dict | None = None


MetricCalculator = Callable[[SortingResult, SequenceBatch], MetricResult]


def _latency(result: SortingResult, _: SequenceBatch) -> MetricResult:
    return MetricResult(name="latency_ms", value=round(result.duration_ms, 3), unit="ms")


def _comparisons(result: SortingResult, _: SequenceBatch) -> MetricResult:
    return MetricResult(name="comparisons", value=result.comparisons)


def _swaps(result: SortingResult, _: SequenceBatch) -> MetricResult:
    return MetricResult(name="swaps", value=result.swaps)


def _sortedness(result: SortingResult, _: SequenceBatch) -> MetricResult:
    is_sorted = all(result.sorted_values[i] <= result.sorted_values[i + 1] for i in range(len(result.sorted_values) - 1))
    return MetricResult(name="is_sorted", value=is_sorted)


def _digit_entropy(_: SortingResult, batch: SequenceBatch) -> MetricResult:
    if not batch.digits:
        return MetricResult(name="digit_entropy", value=0.0)
    counts = {}
    total = 0
    for digits in batch.digits:
        for digit in digits:
            counts[digit] = counts.get(digit, 0) + 1
            total += 1
    entropy = 0.0
    for count in counts.values():
        probability = count / total
        if probability:
            entropy -= probability * math.log2(probability)
    return MetricResult(name="digit_entropy", value=round(entropy, 4))


_METRICS: Dict[str, MetricCalculator] = {
    "latency_ms": _latency,
    "comparisons": _comparisons,
    "swaps": _swaps,
    "is_sorted": _sortedness,
    "digit_entropy": _digit_entropy,
}


def available_metrics() -> List[str]:
    return list(_METRICS.keys())


def compute_metrics(
    result: SortingResult,
    batch: SequenceBatch,
    requested: Iterable[str],
) -> List[MetricResult]:
    metrics: List[MetricResult] = []
    for name in requested:
        calculator = _METRICS.get(name)
        if not calculator:
            continue
        metrics.append(calculator(result, batch))
    return metrics
