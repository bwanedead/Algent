"""
Sorting algorithm implementations with lightweight instrumentation.

Each algorithm complies with the minimal interface defined here so the Algo Lab
experiments can treat them uniformly (counting comparisons, swaps, trace, etc.).
"""
from __future__ import annotations

from dataclasses import dataclass, field
import time
from typing import Callable, Dict, Iterable, List, Protocol


@dataclass
class SortingTraceEvent:
    """Optional trace payload documenting notable steps."""

    action: str
    indices: tuple[int, int] | None = None
    values: tuple[int, int] | None = None


@dataclass
class SortingResult:
    """Result envelope produced by every sorting algorithm."""

    name: str
    input_values: List[int]
    sorted_values: List[int]
    comparisons: int
    swaps: int
    duration_ms: float
    trace: List[SortingTraceEvent] = field(default_factory=list)


@dataclass
class SortingOptions:
    """Execution flags controlling instrumentation."""

    collect_trace: bool = False
    trace_limit: int = 1_000


class SortingAlgorithm(Protocol):
    def __call__(self, values: List[int], options: SortingOptions) -> SortingResult: ...


def sorting_algorithms() -> Dict[str, "AlgorithmDetails"]:
    """Expose metadata for the registry."""
    return _ALGORITHMS


@dataclass
class AlgorithmDetails:
    name: str
    description: str
    runner: SortingAlgorithm


def run_sorting_algorithm(
    name: str,
    values: Iterable[int],
    options: SortingOptions | None = None,
) -> SortingResult:
    algo = _ALGORITHMS.get(name)
    if not algo:
        raise ValueError(f"Unknown sorting algorithm '{name}'")
    return algo.runner(list(values), options or SortingOptions())


def _bubble_sort(values: List[int], options: SortingOptions) -> SortingResult:
    start = time.perf_counter()
    arr = list(values)
    n = len(arr)
    comparisons = 0
    swaps = 0
    trace: List[SortingTraceEvent] = []
    trace_limit = options.trace_limit

    for i in range(n):
        for j in range(0, n - i - 1):
            comparisons += 1
            if arr[j] > arr[j + 1]:
                swaps += 1
                arr[j], arr[j + 1] = arr[j + 1], arr[j]
                if options.collect_trace and len(trace) < trace_limit:
                    trace.append(
                        SortingTraceEvent(
                            action="swap",
                            indices=(j, j + 1),
                            values=(arr[j], arr[j + 1]),
                        ),
                    )
    duration_ms = (time.perf_counter() - start) * 1000.0
    return SortingResult(
        name="bubble_sort",
        input_values=list(values),
        sorted_values=arr,
        comparisons=comparisons,
        swaps=swaps,
        duration_ms=duration_ms,
        trace=trace,
    )


def _insertion_sort(values: List[int], options: SortingOptions) -> SortingResult:
    start = time.perf_counter()
    arr = list(values)
    comparisons = 0
    swaps = 0
    trace: List[SortingTraceEvent] = []
    limit = options.trace_limit

    for i in range(1, len(arr)):
        key = arr[i]
        j = i - 1
        while j >= 0 and arr[j] > key:
            comparisons += 1
            arr[j + 1] = arr[j]
            swaps += 1
            if options.collect_trace and len(trace) < limit:
                trace.append(
                    SortingTraceEvent(
                        action="shift",
                        indices=(j, j + 1),
                        values=(arr[j], key),
                    )
                )
            j -= 1
        arr[j + 1] = key
        if options.collect_trace and len(trace) < limit:
            trace.append(
                SortingTraceEvent(
                    action="insert",
                    indices=(j + 1, i),
                    values=(key, arr[j + 1]),
                )
            )
    duration_ms = (time.perf_counter() - start) * 1000.0
    return SortingResult(
        name="insertion_sort",
        input_values=list(values),
        sorted_values=arr,
        comparisons=comparisons,
        swaps=swaps,
        duration_ms=duration_ms,
        trace=trace,
    )


def _merge_sort(values: List[int], options: SortingOptions) -> SortingResult:
    start = time.perf_counter()
    arr = list(values)
    comparisons = 0
    swaps = 0
    trace: List[SortingTraceEvent] = []
    limit = options.trace_limit

    def merge_sort(data: List[int], depth: int = 0) -> List[int]:
        nonlocal comparisons, swaps, trace
        if len(data) <= 1:
            return data
        mid = len(data) // 2
        left = merge_sort(data[:mid], depth + 1)
        right = merge_sort(data[mid:], depth + 1)
        merged: List[int] = []
        i = j = 0
        while i < len(left) and j < len(right):
            comparisons += 1
            if left[i] <= right[j]:
                merged.append(left[i])
                i += 1
            else:
                merged.append(right[j])
                j += 1
            swaps += 1
        merged.extend(left[i:])
        merged.extend(right[j:])
        if options.collect_trace and len(trace) < limit:
            trace.append(
                SortingTraceEvent(
                    action="merge",
                    values=(min(merged), max(merged)),
                )
            )
        return merged

    sorted_arr = merge_sort(arr)
    duration_ms = (time.perf_counter() - start) * 1000.0
    return SortingResult(
        name="merge_sort",
        input_values=list(values),
        sorted_values=sorted_arr,
        comparisons=comparisons,
        swaps=swaps,
        duration_ms=duration_ms,
        trace=trace,
    )


_ALGORITHMS: Dict[str, AlgorithmDetails] = {
    "bubble_sort": AlgorithmDetails(
        name="bubble_sort",
        description="O(n^2) educational bubble sort with swap instrumentation.",
        runner=_bubble_sort,
    ),
    "insertion_sort": AlgorithmDetails(
        name="insertion_sort",
        description="Stable insertion sort suitable for small vectors.",
        runner=_insertion_sort,
    ),
    "merge_sort": AlgorithmDetails(
        name="merge_sort",
        description="Divide-and-conquer merge sort with minimal instrumentation.",
        runner=_merge_sort,
    ),
}
