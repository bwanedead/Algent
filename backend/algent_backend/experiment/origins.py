"""
Origin chains (evidence independence, framework section 7): which documents are one voice repeated and which are independent. Deterministic, no model.

Two documents share a chain when they have the same canonical URL, or near-identical text (shared 4-word shingles, Jaccard >= ``flags.DUP_JACCARD``, only for
texts long enough to mean it). Chains are the connected components of those links, computed over the documents visible at the cutoff only (so a later repeat
cannot reshape an earlier chain). The earliest document (by publish time, then id) is the chain's origin; every other member's ``origin_chain`` names it.
Nothing is removed: repeats carry timing and amplification signal, and a protocol may weigh them as it likes. This is a versioned L2 method (``METHOD``).
"""

from __future__ import annotations

import hashlib
import re
from collections import defaultdict
from urllib.parse import parse_qsl, urlsplit

from . import flags
from .contracts import Evidence

METHOD = "origin-chain@1"
_SKETCH = 16                 # smallest shingle hashes kept per document: two near-duplicates almost always share one, so candidates are found without comparing every pair
_SHINGLE = 4
_MIN_WORDS = 12              # shorter texts are never matched by text (a headline or a one-liner repeats by accident)
_TRACKING = ("utm_", "fbclid", "gclid", "mc_", "ref", "source")


def canonical_url(url: str) -> str:
    """Host (no www) + path (no trailing slash) + the non-tracking query, lowercased; '' when there is no usable URL."""
    u = (url or "").strip()
    if not u:
        return ""
    p = urlsplit(u if "//" in u else "//" + u)
    host = p.netloc.lower().removeprefix("www.")
    if not host:
        return ""
    q = "&".join(f"{k}={v}" for k, v in sorted(parse_qsl(p.query)) if not k.lower().startswith(_TRACKING))
    return f"{host}{p.path.rstrip('/').lower()}" + (f"?{q}" if q else "")


def _words(e: Evidence) -> list[str]:
    return re.findall(r"[a-z0-9]+", f"{e.title} {e.body}".lower())


def _shingles(words: list[str]) -> set[int]:
    return {int.from_bytes(hashlib.blake2b(" ".join(words[i:i + _SHINGLE]).encode(), digest_size=8).digest(), "big") for i in range(len(words) - _SHINGLE + 1)}


def chains(items: list[Evidence]) -> dict[str, str]:
    """{document id: chain id}. A chain id is the origin document's id; a document linked to nothing is its own chain."""
    order = sorted(items, key=lambda e: (e.publish_time, e.id))
    parent = {e.id: e.id for e in order}

    def find(x: str) -> str:
        while parent[x] != x:
            parent[x] = parent[parent[x]]
            x = parent[x]
        return x

    def union(a: str, b: str) -> None:
        ra, rb = find(a), find(b)
        if ra != rb:
            parent[max(ra, rb)] = min(ra, rb)                  # the earlier-sorting id stays the root (fixed below to the earliest by publish time)

    by_url: dict[str, str] = {}
    sets: dict[str, set[int]] = {}
    buckets: dict[int, list[str]] = defaultdict(list)
    for e in order:
        u = canonical_url(e.url)
        if u:
            union(e.id, by_url.setdefault(u, e.id))
        w = _words(e)
        if len(w) >= _MIN_WORDS:
            sets[e.id] = s = _shingles(w)
            for h in sorted(s)[:_SKETCH]:
                buckets[h].append(e.id)
    seen: set[tuple[str, str]] = set()
    for ids in buckets.values():
        for i, a in enumerate(ids):
            for b in ids[i + 1:]:
                if (a, b) in seen or find(a) == find(b):
                    continue
                seen.add((a, b))
                inter = len(sets[a] & sets[b])
                if inter and inter / len(sets[a] | sets[b]) >= flags.DUP_JACCARD:
                    union(a, b)
    members: dict[str, list[str]] = defaultdict(list)
    for e in order:
        members[find(e.id)].append(e.id)
    return {i: grp[0] for grp in members.values() for i in grp}       # ``order`` is publish-time ascending, so grp[0] is the earliest


def annotate(items: list[Evidence]) -> list[Evidence]:
    """Copies of ``items`` with ``origin_chain`` set: [] for an origin, [origin id] for a repeat."""
    cid = chains(items)
    return [e.model_copy(update={"origin_chain": [] if cid[e.id] == e.id else [cid[e.id]]}) for e in items]


def summary(shown: list[Evidence]) -> dict[str, object]:
    """How many of the shown documents are independent voices: distinct chains (a document with no chain data counts as its own)."""
    keys = {(e.origin_chain[0] if e.origin_chain else e.id) for e in shown}
    return {"method": METHOD, "n_shown": len(shown), "n_independent": len(keys)}
