"""Strict JSON decoding and number checks shared by the Ohmega Research readers.

Mechanical only. Each reader owns its schema: which fields exist, which may be null, and what
they mean.
"""

from __future__ import annotations

import json
import math


def loads(text: str) -> object:
    """Decode JSON, rejecting duplicate keys and NaN/Infinity with a ``ValueError``."""
    return json.loads(text, parse_constant=_reject_constant, object_pairs_hook=_unique_keys)


def parse_amount(value: object) -> tuple[float | None, str | None]:
    """Return ``(number, None)`` for a finite, non-negative number, else ``(None, problem)``."""
    if isinstance(value, bool) or not isinstance(value, int | float):
        return None, "must be a number (booleans and strings are not numbers)"
    try:
        as_float = float(value)
    except OverflowError:
        return None, "must be finite"
    if not math.isfinite(as_float):
        return None, "must be finite"
    if as_float < 0:
        return None, "must be non-negative"
    return as_float, None


def _reject_constant(name: str) -> float:
    raise ValueError(f"non-finite number {name} is not allowed")


def _unique_keys(pairs: list[tuple[str, object]]) -> dict[str, object]:
    obj: dict[str, object] = {}
    for key, value in pairs:
        if key in obj:
            raise ValueError(f"duplicate key {key!r}")
        obj[key] = value
    return obj
