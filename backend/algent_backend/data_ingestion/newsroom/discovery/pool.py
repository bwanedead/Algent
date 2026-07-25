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
from .stories import url_slug_label

# The GKG theme-pillar vocabulary (economy/…) vs the beat vocabulary (economics/…)
# overlap; alias the trivial cases so a slice lines up across channels.
_PILLAR_ALIAS = {"economy": "economics"}


def build_pool(
    insights: InsightsReport | None,
    sheet: BeatSheet | None,
    markets: list[dict] | None = None,
    x_hits: list[dict] | None = None,
    *,
    gkg_limit: int | None = None,
    markets_limit: int | None = None,
    beats_limit: int | None = None,
) -> DiscoveryPool:
    """Consolidate the net + sweep + prediction markets + X into one grounded pool.

    Optional ``gkg_limit`` / ``markets_limit`` rebalance when the X novelty valve is
    on so wire/market mass cannot drown platform-native leads. ``beats_limit`` caps
    the swept registry, which is the opposite problem: 40 beats × 25 records is an
    order of magnitude more than a pool should carry, so it is taken round-robin.
    """
    items: list[PoolItem] = []
    if insights is not None:
        gkg = list(insights.candidates)
        if gkg_limit is not None:
            gkg = gkg[: max(0, gkg_limit)]
        items.extend(_gkg_item(c) for c in gkg)
    if sheet is not None:
        items.extend(_beat_items(sheet, beats_limit))
    if markets:
        from ..topic_filters import is_sports_text

        mk = [
            m for m in markets
            if not is_sports_text(str(m.get("question") or ""))
        ]
        if markets_limit is not None:
            mk = mk[: max(0, markets_limit)]
        items.extend(_market_item(m) for m in mk)
    if x_hits:
        items.extend(_x_item(h) for h in x_hits)

    # Echoes are a cross-channel problem, not a sweep problem. Polymarket lists every
    # outcome of one question as its own market (five "Fed July decision" rows, four
    # "ceasefire holds through <date>" rows), and the same wire story reaches the X band
    # from two accounts. Suppressing per channel left all of that in the menu, so the
    # pass runs once over everything, after the channels are merged.
    items = _drop_echoes(items)

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


def _market_item(market: dict) -> PoolItem:
    """A prediction market as a pool item — a forward-looking story lead."""
    return PoolItem(
        id=f"market:{market.get('source', 'pm')}:{market.get('url', '')[-40:]}",
        label=market.get("question", ""),
        channel="market",
        kind="market",
        signals={
            "last_price": market.get("last_price"),
            "volume_24h": market.get("volume_24h"),
            "price_change_1d": market.get("price_change_1d"),
        },
        evidence=[BeatHit(title=market.get("question", ""), url=market.get("url", ""))],
    )


def _x_item(hit: dict) -> PoolItem:
    """An X hit as a pool item — API posts (primary) or optional Grok-curated topics.

    ``pre_vetted`` is True only when an upstream LLM already judged significance
    (Grok CLI path). Raw X API posts stay ``pre_vetted=False`` so rake/synthesis
    still triage them. Engagement metrics ride in signals for ranking later.
    """
    topic = str(hit.get("topic") or "").strip()
    urls = [u for u in (hit.get("urls") or []) if isinstance(u, str)][:3]
    src = str(hit.get("source") or "x")
    # Stable-ish id: prefer post URL tail, else trend/topic slug.
    if urls and "/status/" in urls[0]:
        sid = urls[0].rstrip("/").rsplit("/", 1)[-1]
        item_id = f"x:{src}:{sid}"
    else:
        slug = "".join(ch if ch.isalnum() else "_" for ch in topic.lower())[:48]
        item_id = f"x:{src}:{slug or 'topic'}"
    pre = hit.get("pre_vetted")
    if pre is None:
        pre = src in ("x_grok", "grok")  # only LLM-curated paths skip re-rake
    if src in ("x_news",):
        kind = "news"
    elif src in ("x_ai_pulse",):
        # Dedicated AI eyeballs (labs/people/AI news) — still rake unless pre_vetted
        kind = "news" if str(hit.get("lane") or "").startswith("ai_news:") else "post"
    elif src in ("x_novelty",):
        kind = "post"  # engagement-ranked event probes — novelty valve
    elif src in ("x_spectrum",):
        kind = "post"  # multi-angle independent / OSINT voices
    elif src in ("x_aggregator",):
        kind = "post"  # general wire posts — still rake/synthesis triage
    elif src in ("x_grok", "grok") or pre:
        kind = "trending"
    else:
        kind = "post"
    return PoolItem(
        id=item_id,
        label=topic,
        channel="x",
        kind=kind,
        signals={
            "summary": str(hit.get("summary") or "").strip(),
            "lane": str(hit.get("lane") or ""),
            "author": str(hit.get("author") or ""),
            "likes": hit.get("likes"),
            "reposts": hit.get("reposts"),
            "tweet_count": hit.get("tweet_count"),
            "pre_vetted": bool(pre),
        },
        evidence=[BeatHit(title=topic[:140], url=u) for u in urls],
    )


# GDELT GKG theme codes lead with a taxonomy prefix (+ sometimes a numeric id) that
# carries no meaning for a reader: WB_2811_COLLECTIVE_BARGAINING, TAX_DISEASE_COMA.
# We humanize the label so the agents have something legible to start from; rake then
# upgrades it to the real article headline. The raw code is kept in signals.
_THEME_PREFIXES = frozenset({
    "WB", "TAX", "ECON", "EPU", "ENV", "GOV", "MANMADE", "NATURAL", "CRISISLEX",
    "SOC", "UNGP", "WTO", "GENERAL", "POLICY", "EPU_POLICY", "FNCACT",
})


def _humanize_theme(code: str) -> str:
    """`WB_2811_COLLECTIVE_BARGAINING` -> `collective bargaining`. Best-effort."""
    parts = code.split("_")
    while parts and (parts[0] in _THEME_PREFIXES or parts[0].isdigit()):
        parts.pop(0)
    return " ".join(parts).lower() if parts else code.lower()


def _gkg_item(candidate) -> PoolItem:
    pillars = [_PILLAR_ALIAS.get(candidate.pillar, candidate.pillar)] if candidate.pillar else []
    # Story/event keys are already human; themes get a readable label (raw code
    # stays in signals); named entities keep their key as-is.
    if candidate.kind in ("story", "event"):
        label = candidate.key
    elif candidate.kind == "theme":
        label = _humanize_theme(candidate.key)
    else:
        label = candidate.key
    # Prefer a URL-slug title on evidence when the candidate is still a bare theme.
    evidence: list[BeatHit] = []
    for url in candidate.examples:
        title = label
        if candidate.kind == "theme":
            slug = url_slug_label(url)
            if slug:
                title = slug
        evidence.append(BeatHit(title=title[:160], url=url))
    return PoolItem(
        id=f"gkg:{candidate.kind}:{_id_slug(candidate.kind, candidate.key)}",
        label=label,
        channel="gkg",
        kind=candidate.kind,
        pillars=pillars,
        scope=list(candidate.languages),
        signals={
            "theme_code": candidate.key if candidate.kind == "theme" else None,
            "velocity": candidate.velocity,
            "rising": candidate.rising,
            "novel": candidate.novel,
            "count": candidate.count,
            "language_count": candidate.language_count,
            "avg_tone": candidate.avg_tone,
            "score": candidate.score,
            # Scalar only (PoolItem.signals values are str|float|int|bool).
            "reasons": (
                ",".join(candidate.reasons)
                if getattr(candidate, "reasons", None)
                else None
            ),
        },
        evidence=evidence,
        related=list(candidate.related),
    )


def _id_slug(kind: str, key: str) -> str:
    """Stable-ish id fragment; story/event keys can be long."""
    raw = key if kind in ("theme", "person", "organization") else key[:80]
    return "".join(ch if ch.isalnum() or ch in "._-+ " else "_" for ch in raw).strip()[:96]


def _beat_items(sheet: BeatSheet, limit: int | None = None) -> list[PoolItem]:
    """Swept articles, de-duplicated, then narrowed to the cap by *dissimilarity*.

    The sweep returns far more than a pool should carry, so something has to be
    dropped — and what gets dropped is redundancy: :func:`_diversify` keeps the
    stories least like the ones already kept. The query that fetched an article is
    deliberately *not* part of that decision. A query is a net cast into a different
    part of the corpus, not a category owed representation; selecting one-per-query
    would only trade a wire rut for a taxonomy rut.
    """
    from ..topic_filters import is_non_news_topic

    seen: dict[str, PoolItem] = {}
    items: list[PoolItem] = []
    for result in sheet.results:
        for hit in result.hits:
            # The sweep was the one channel with no denylist: X, markets and GKG
            # entities all screen here, so a `world_events` or country query was
            # free to hand us match reports and ticker-mill SEO.
            if is_non_news_topic(hit.title):
                continue
            keys = _dedupe_keys(result, hit)
            existing = next((seen[k] for k in keys if k in seen), None)
            if existing is None:
                item = _new_beat_item(result, hit)
                for key in keys:
                    seen[key] = item
                items.append(item)
            else:
                # A story found by more than one query keeps every tag it earned.
                _merge_tags(existing, result, hit)
    return _diversify(items, limit)


def _dedupe_keys(result, hit) -> list[str]:
    """The identities one article can arrive under: its URL, and its headline.

    URL alone is not enough. A wire story is syndicated to a dozen outlets under the
    same headline at different URLs, and each copy would otherwise spend a slot in a
    capped pool — three of the same measles headline is not three leads.
    """
    keys = [f"u:{hit.url}"] if hit.url else []
    title = _title_key(hit.title)
    keys.append(f"t:{title}" if title else f"b:{result.beat_id}:{hit.title}")
    return keys


def _title_key(title: str) -> str:
    """Headline down to its words, so two renderings of one headline collide.

    GDELT spaces punctuation out, and inconsistently: the same wire story arrives as
    "U . S . measles cases" from one outlet and "US measles cases" from the next. So
    words are split on punctuation and then runs of single letters are glued back
    into the initialism they came from (``u s`` -> ``us``).
    """
    merged: list[str] = []
    in_initialism = False
    for word in "".join(ch if ch.isalnum() else " " for ch in title.lower()).split():
        if len(word) == 1 and word.isalpha():
            if in_initialism:
                merged[-1] += word
            else:
                merged.append(word)
                in_initialism = True
        else:
            merged.append(word)
            in_initialism = False
    return " ".join(merged)


# Words too common to say anything about what a story is about.
_STOP = frozenset(
    "the a an and or of in on to for with as at by from is are was were be been being "
    "it its this that these those has have had will would can could may might not new "
    "after over amid says said say report reports first than into out about more most"
    .split()
)


# How much headline vocabulary two stories must share to count as the same story
# told twice. High on purpose: this drops echoes, it does not rank topics.
_ECHO_OVERLAP = 0.6


def _drop_echoes(items: list[PoolItem]) -> list[PoolItem]:
    """Keep the first telling of each story, drop the retellings. No cap, no reordering.

    Same rule as inside the sweep cap, applied to the merged pool so it also catches
    the cross-channel echoes: a market's five outcome rows for one decision, or one wire
    story arriving from two X accounts.
    """
    kept: list[PoolItem] = []
    kept_terms: list[frozenset[str]] = []
    for item in items:
        terms = _terms(item)
        if terms and any(_overlap(terms, held) >= _ECHO_OVERLAP for held in kept_terms):
            continue
        kept.append(item)
        kept_terms.append(terms)
    return kept


def _diversify(items: list[PoolItem], limit: int | None) -> list[PoolItem]:
    """Fill the cap with distinct stories, dropping the echoes.

    Two jobs, deliberately separated, because only one of them can be done honestly
    from a bare headline:

    1. **Drop echoes** — a story already held in near-identical words is skipped.
       This is the real work: a running story arrives as twenty rewrites of one
       line ("US measles cases pass 2025 record" ×12), and without this they eat
       the pool. Overlap of headline vocabulary is reliable evidence for *this*.
    2. **Truncate fairly** — the survivors are walked in a source-interleaved
       order, so that when the cap bites it is not simply whichever query happened
       to sort first that wins everything.

    What this deliberately does NOT do is rank topics against each other. Two
    attempts to score "interestingness" lexically both failed on real data: ranking
    by unseen words handed 27 of 28 slots to the first two queries in the list, and
    ranking by rare vocabulary handed 12 slots to one query because non-Latin
    scripts share no tokens with anything and so always look maximally novel. A
    headline cannot tell us which of two unlike stories is the better lead — the
    synthesis agent reads these titles next and can actually judge. This layer
    organizes and grounds; it does not judge (see the module docstring).

    Still no quota: nothing is owed a slot, and a query whose hits are all echoes of
    what we already hold contributes nothing.
    """
    if limit is None or len(items) <= limit:
        return items

    chosen: list[PoolItem] = []
    kept_terms: list[frozenset[str]] = []
    for item in _interleaved_by_source(items):
        terms = _terms(item)
        if terms and any(_overlap(terms, held) >= _ECHO_OVERLAP for held in kept_terms):
            continue
        chosen.append(item)
        kept_terms.append(terms)
        if len(chosen) >= limit:
            break
    return chosen


def _overlap(terms: frozenset[str], other: frozenset[str]) -> float:
    """Share of the smaller headline's vocabulary the two have in common."""
    if not terms or not other:
        return 0.0
    return len(terms & other) / min(len(terms), len(other))


def _interleaved_by_source(items: list[PoolItem]) -> list[PoolItem]:
    """Round-robin over the query that found each item — an ordering device only.

    This is not representation: nothing here reserves a slot or drops an item. It
    only decides *what order the cap eats in*, so truncation reflects the day's
    material rather than the registry's declaration order.
    """
    queues: dict[str, list[PoolItem]] = defaultdict(list)
    for item in items:
        queues[item.signals.get("found_by") or ""].append(item)
    ordered: list[PoolItem] = []
    for rank in range(max((len(q) for q in queues.values()), default=0)):
        ordered.extend(q[rank] for q in queues.values() if rank < len(q))
    return ordered


def _terms(item: PoolItem) -> frozenset[str]:
    """A headline's content words — what one story's overlap with another is judged on."""
    return frozenset(
        word for word in _title_key(item.label).split()
        if len(word) > 3 and word not in _STOP
    )


def _new_beat_item(result, hit) -> PoolItem:
    return PoolItem(
        id=f"beat:{hit.url or result.beat_id}",
        label=hit.title,
        channel="beat",
        kind="article",
        pillars=[result.pillar] if result.pillar else [],
        scope=[hit.country] if hit.country else [],
        signals={
            "domain": hit.domain, "seendate": hit.seendate, "language": hit.language,
            # Which query surfaced it — used only to interleave before the cap bites.
            "found_by": result.beat_id,
        },
        evidence=[hit],
    )


def _merge_tags(item: PoolItem, result, hit) -> None:
    if result.pillar and result.pillar not in item.pillars:
        item.pillars.append(result.pillar)
    if hit.country and hit.country not in item.scope:
        item.scope.append(hit.country)
