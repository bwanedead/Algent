"""
Shared type definitions for Algo Lab algorithm registry.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Callable, Iterable

from .sorting import SortingOptions, SortingResult

AlgorithmRunner = Callable[[Iterable[int], SortingOptions], SortingResult]


@dataclass
class AlgorithmDescriptor:
    """Lightweight descriptor used for discovery."""

    name: str
    kind: str
    description: str
