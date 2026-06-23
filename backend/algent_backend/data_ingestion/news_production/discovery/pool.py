"""
Pool consolidation — fold the GKG net + the DOC beat sweep into one candidate pool.

This is leg 1 of the funnel: turn two differently-shaped artifacts (a velocity-
ranked :class:`InsightsReport` and a tagged :class:`BeatSheet`) into a single
:class:`DiscoveryPool` the synthesis agent can read. It *organizes and grounds* —
it does not judge. Cross-channel story fusion (this GKG entity == that beat
article) is left to the agent, which can read titles; deterministic linking has no
shared key to do it reliably. What we do deterministically and well:

- normalise both channels to one :class:`PoolItem` shape;
- de-duplicate beat articles that recur across beats (one item, merged pillars);
- align the two pillar vocabularies where they trivially overlap;
- build a pillar facet index so any slice (economics, …) is one lookup.

Pure: artifacts in, pool out. No I/O.
"""

from __future__ import annotations

from collections import Counter, defaultdict
from datetime import UTC, datetime

from .report import BeatHit, BeatSheet, DiscoveryPool, InsightsReport, PoolItem

# The GKG theme-pillar vocabulary (economy/…) vs the beat vocabulary (economics/…)
# overlap; alias the trivial cases so a slice lines up across channels.
_PILLAR_ALIAS = {"economy": "economics"}


def build_pool(
    insights: InsightsReport | None, sheet: BeatSheet | None
) -> DiscoveryPool:
    """Consolidate the net + sweep into one grounded, tagged pool."""
    items: list[PoolItem] = []
    if insights is not None:
        items.extend(_gkg_item(c) for c in insights.candidates)
    if sheet is not None:
        items.extend(_beat_items(sheet))

    facets: dict[str, list[str]] = defaultdict(list)
    for item in items:
        for pillar in item.pillars:
            facets[pillar].append(item.id)

    return DiscoveryPool(
        generated_at=datetime.now(UTC).isoformat(),
        gkg_batch_id=insights.batch_id if insights else None,
        beat_sheet_at=sheet.generated_at if sheet else None,
        item_count=len(items),
        by_channel=dict(Counter(i.channel for i in items)),
        by_pillar={p: len(ids) for p, ids in facets.items()},
        facets=dict(facets),
        items=items,
    )


def _gkg_item(candidate) -> PoolItem:
    pillars = [_PILLAR_ALIAS.get(candidate.pillar, candidate.pillar)] if candidate.pillar else []
    return PoolItem(
        id=f"gkg:{candidate.kind}:{candidate.key}",
        label=candidate.key,
        channel="gkg",
        kind=candidate.kind,
        pillars=pillars,
        scope=list(candidate.languages),
        signals={
            "velocity": candidate.velocity,
            "rising": candidate.rising,
            "novel": candidate.novel,
            "count": candidate.count,
            "language_count": candidate.language_count,
            "avg_tone": candidate.avg_tone,
            "score": candidate.score,
        },
        # Example source articles so the agent can free-fetch GKG items, same as beats.
        evidence=[BeatHit(title=candidate.key, url=url) for url in candidate.examples],
        related=list(candidate.related),
    )


def _beat_items(sheet: BeatSheet) -> list[PoolItem]:
    """Beat articles, de-duplicated across beats by URL (merging pillars/scope)."""
    by_url: dict[str, PoolItem] = {}
    for result in sheet.results:
        for hit in result.hits:
            key = hit.url or f"{result.beat_id}:{hit.title}"
            existing = by_url.get(key)
            if existing is None:
                by_url[key] = _new_beat_item(result, hit)
            else:
                _merge_tags(existing, result, hit)
    return list(by_url.values())


def _new_beat_item(result, hit) -> PoolItem:
    return PoolItem(
        id=f"beat:{hit.url or result.beat_id}",
        label=hit.title,
        channel="beat",
        kind="article",
        pillars=[result.pillar] if result.pillar else [],
        scope=[hit.country] if hit.country else [],
        signals={"domain": hit.domain, "seendate": hit.seendate, "language": hit.language},
        evidence=[hit],
    )


def _merge_tags(item: PoolItem, result, hit) -> None:
    if result.pillar and result.pillar not in item.pillars:
        item.pillars.append(result.pillar)
    if hit.country and hit.country not in item.scope:
        item.scope.append(hit.country)
