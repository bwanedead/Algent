"""
Robust statistics — the median / MAD "normal" of a count and how far a value sits from it (pure; no I/O).

The normal is the MEDIAN of what the same hour of the week held in earlier weeks, and its spread the MAD (median absolute
deviation): one odd week, or an incident that was itself flagged, moves neither. The score is the modified z-score
``(x - median) / sigma``; ``sigma`` is ``1.4826 * MAD`` (the factor that makes MAD comparable to a standard deviation for
bell-shaped noise) but never less than the damped counting spread of the median (``POISSON_SHARE * sqrt(median)``) nor 1: identical
weeks must not give a zero spread, and a change of less than one object is never an event. See ``flags.py`` for the thresholds.
"""

from __future__ import annotations

import math
from typing import NamedTuple, Sequence

from . import flags

MAD_TO_SIGMA = 1.4826


class Normal(NamedTuple):
    median: float
    sigma: float
    n: int                  # values the estimate rests on
    learning: bool          # True: fewer than the full set of weeks (a trailing-days fallback)


def median(xs: Sequence[float]) -> float:
    s = sorted(xs)
    m = len(s) // 2
    return float(s[m]) if len(s) % 2 else (s[m - 1] + s[m]) / 2.0


def sigma_of(med: float, mad: float) -> float:
    return max(MAD_TO_SIGMA * mad, flags.POISSON_SHARE * math.sqrt(max(med, 0.0)), 1.0)


def normal_of(values: Sequence[float], *, learning: bool = False) -> Normal | None:
    """The robust normal of ``values`` (None when there are none)."""
    if not values:
        return None
    med = median(values)
    mad = median([abs(v - med) for v in values])
    return Normal(med, sigma_of(med, mad), len(values), learning)


def zero_normal() -> Normal:
    """The normal of a place that has never held anything while the layer was being watched: nothing, with the unit spread."""
    return Normal(0.0, 1.0, 0, False)


def score(x: float, normal: Normal) -> float:
    return (x - normal.median) / normal.sigma


def ratio(x: float, normal: Normal) -> float | None:
    """How many times normal the value is (None when normal is about zero: the ratio would say nothing)."""
    return x / normal.median if normal.median >= 1.0 else None
