"""
Dataset generation utilities for Algo Lab experiments.

The goal is to keep dataset construction deterministic and reproducible so that
automated agents can reason about experiment outcomes. All random operations
accept a seed to ensure repeatability.
"""
from __future__ import annotations

from dataclasses import dataclass, field
import random
from typing import List


@dataclass
class SequenceSpec:
    """Defines the characteristics of an integer sequence used in experiments."""

    size: int = 128
    min_value: int = 0
    max_value: int = 999
    allow_duplicates: bool = True
    nearly_sorted_ratio: float = 0.0
    reversed: bool = False
    digit_width: int | None = None
    seed: int | None = None

    def validate(self) -> None:
        if self.size <= 0:
            raise ValueError("size must be positive")
        if self.min_value > self.max_value:
            raise ValueError("min_value must be <= max_value")
        if not self.allow_duplicates and self.size > (self.max_value - self.min_value + 1):
            raise ValueError("Cannot request unique sequence larger than range")
        if not (0.0 <= self.nearly_sorted_ratio <= 1.0):
            raise ValueError("nearly_sorted_ratio must be between 0 and 1")


@dataclass
class SequenceBatch:
    """Concrete dataset ready for execution."""

    spec: SequenceSpec
    values: List[int]
    digits: List[List[int]] = field(default_factory=list)

    def summary(self) -> dict:
        return {
            "size": len(self.values),
            "min": min(self.values) if self.values else None,
            "max": max(self.values) if self.values else None,
            "digits": self.digits[: min(5, len(self.digits))],
        }


def generate_sequence(spec: SequenceSpec) -> SequenceBatch:
    """Produce a numeric sequence respecting the provided spec."""
    spec.validate()
    rng = random.Random(spec.seed)
    if spec.allow_duplicates:
        values = [rng.randint(spec.min_value, spec.max_value) for _ in range(spec.size)]
    else:
        values = rng.sample(range(spec.min_value, spec.max_value + 1), spec.size)

    if spec.nearly_sorted_ratio > 0:
        values.sort()
        swaps = max(1, int(spec.size * spec.nearly_sorted_ratio))
        for _ in range(swaps):
            i = rng.randrange(0, spec.size)
            j = rng.randrange(0, spec.size)
            values[i], values[j] = values[j], values[i]
    elif spec.reversed:
        values.sort(reverse=True)

    digits: List[List[int]] = []
    if spec.digit_width:
        width = spec.digit_width
        for value in values:
            digits.append([int(ch) for ch in f"{value:0{width}d}"])

    return SequenceBatch(spec=spec, values=values, digits=digits)
