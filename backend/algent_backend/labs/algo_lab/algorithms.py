"""
Algorithm registry for Algo Lab.

This module keeps the registry intentionally lightweight so that experiments can
resolve algorithms without importing concrete implementations directly. Each
algorithm operates on primitive Python collections, which keeps the dependency
surface tiny and easy to reason about.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Callable, Dict, Iterable, List

from .algorithms.sorting import (
    SortingOptions,
    SortingResult,
    run_sorting_algorithm,
    sorting_algorithms,
)


AlgorithmRunner = Callable[[Iterable[int], SortingOptions], SortingResult]


@dataclass
class AlgorithmDescriptor:
    """Lightweight descriptor used for discovery."""

    name: str
    kind: str
    description: str


_REGISTRY: Dict[str, AlgorithmDescriptor] = {
    name: AlgorithmDescriptor(
        name=name,
        kind="sorting",
        description=details.description,
    )
    for name, details in sorting_algorithms().items()
}


def list_available(kind: str | None = None) -> List[AlgorithmDescriptor]:
    """
    Return available algorithms, optionally filtered by kind (e.g., "sorting").
    """
    if kind is None:
        return list(_REGISTRY.values())
    return [descriptor for descriptor in _REGISTRY.values() if descriptor.kind == kind]


def run(
    name: str,
    data: Iterable[int],
    options: SortingOptions | None = None,
) -> SortingResult:
    """
    Execute an algorithm by name.

    Raises:
        ValueError: if the algorithm is unknown.
    """
    descriptor = _REGISTRY.get(name)
    if not descriptor:
        raise ValueError(f"Unknown algorithm '{name}'. Known algorithms: {sorted(_REGISTRY)}")
    if descriptor.kind == "sorting":
        return run_sorting_algorithm(
            name=name,
            values=data,
            options=options or SortingOptions(),
        )
    raise ValueError(f"Unsupported algorithm kind '{descriptor.kind}' for algorithm '{name}'")
