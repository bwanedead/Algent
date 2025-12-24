"""
Algorithm registry and execution helpers.
"""
from __future__ import annotations

from typing import Dict, Iterable, List

from .sorting import (
    SortingOptions,
    SortingResult,
    run_sorting_algorithm,
    sorting_algorithms,
)
from .types import AlgorithmDescriptor


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
