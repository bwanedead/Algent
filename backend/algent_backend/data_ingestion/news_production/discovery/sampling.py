"""
Stratified reservoir sampling — the engineered-serendipity slice.

A plain random sample of a news firehose just resamples the loud middle. To make
the slice an *anti-rut* force we stratify: keep a small per-key reservoir (key =
language) so rare languages get equal footing, then draw the final slice from
that balanced pool. The result over-represents the margins on purpose.

Single streaming pass, O(keys × cap) memory — nothing is materialised in full.
Generic over item type; the caller supplies the stratification key.
"""

from __future__ import annotations

import random
from collections.abc import Callable, Hashable, Iterable
from typing import TypeVar

T = TypeVar("T")


def stratified_reservoir(
    items: Iterable[T],
    *,
    size: int,
    key: Callable[[T], Hashable],
    per_key_cap: int = 5,
    rng: random.Random | None = None,
) -> list[T]:
    """Return up to ``size`` items, balanced across the values of ``key``.

    Each key keeps an unbiased reservoir of at most ``per_key_cap`` items; the
    final slice is drawn from the union of those reservoirs, so no single key
    (language) can dominate.
    """
    rng = rng or random.Random()
    buckets: dict[Hashable, list[T]] = {}
    seen: dict[Hashable, int] = {}

    for item in items:
        k = key(item)
        n = seen.get(k, 0)
        seen[k] = n + 1
        bucket = buckets.setdefault(k, [])
        if len(bucket) < per_key_cap:
            bucket.append(item)
        else:
            j = rng.randint(0, n)  # classic reservoir replacement
            if j < per_key_cap:
                bucket[j] = item

    pool = [item for bucket in buckets.values() for item in bucket]
    if len(pool) > size:
        pool = rng.sample(pool, size)
    rng.shuffle(pool)
    return pool
