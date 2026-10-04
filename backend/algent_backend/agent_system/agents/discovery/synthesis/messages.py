"""
The synthesis task message — the per-run t0 payload handed to the model.

The system prompt (``prompts.py``) is fixed identity/doctrine; this renders the
**t0 payload** (the discovery pool) into a compact, scannable block the model
triages. Each line is one candidate hit with the free signals already attached,
so the model can triage and decide what to double-click *before* spending a tool
call. Kept terse on purpose — t0 can be ~100+ items.
"""

from __future__ import annotations

from typing import Any

_MAX_ITEMS = 150


def build_t0_message(
    pool: dict[str, Any],
    *,
    recent_headlines: tuple[tuple[str, str], ...] | list[tuple[str, str]] = (),
) -> str:
    """Render a t0 ``DiscoveryPool`` dict into the run's task message.

    X items are listed in a dedicated **novelty band** first so synthesis treats
    the X channel as a first-class valve, not garnish on GKG mass.

    ``recent_headlines`` is the cooldown payload (date, title): prefer not to
    rebuild the same story-family as something we just published.
    """
    items = pool.get("items", [])[:_MAX_ITEMS]
    x_items = [i for i in items if str(i.get("channel") or "") == "x"]
    other = [i for i in items if str(i.get("channel") or "") != "x"]
    lines = [
        "# t0 DISCOVERY POOL (your input to triage)",
        f"items: {pool.get('item_count', len(items))}   "
        f"channels: {pool.get('by_channel', {})}   pillars: {pool.get('by_pillar', {})}",
        f"t0_ref: {pool.get('gkg_batch_id') or pool.get('generated_at', '?')}",
        "",
        "Each line is a candidate hit: [id] label | tags | signals | evidence.",
        "",
    ]
    if recent_headlines:
        lines.append("# ALREADY COVERED — recent published headlines (cooldown)")
        lines.append(
            "Prefer vectors that are NOT the same story-family as these. A reframe or "
            "updated figures on the same development is still the same family — skip it "
            "unless there is a true structural delta. Do not spend the portfolio on "
            "repetition of what we just published."
        )
        for when, title in recent_headlines:
            lines.append(f"- {str(when)[:10]}  {title}")
        lines.append("")
    if x_items:
        lines.append(
            f"## X NOVELTY BAND ({len(x_items)} hits) — platform-native / wires / AI pulse"
        )
        lines.append(
            "Prefer vectors whose *primary* supporting hits are these when they are real "
            "developments. Do not only use X as a footnote on GKG mega-beats."
        )
        lines.extend(_fmt_item(item) for item in x_items)
        lines.append("")
    if other:
        lines.append(f"## OTHER CHANNELS ({len(other)} hits) — gkg / markets / beats / backfeed")
        lines.extend(_fmt_item(item) for item in other)
        lines.append("")
    lines.append(_directive())
    return "\n".join(lines)


def _fmt_item(item: dict[str, Any]) -> str:
    sig = item.get("signals", {}) or {}
    bits = []
    for key in ("velocity", "rising", "novel", "language_count", "avg_tone", "count"):
        if sig.get(key) not in (None, False):
            bits.append(f"{key}={sig[key]}")
    # Provenance for X items. t0 filters nothing, so YOU are the stage that decides what a
    # post is worth — and that needs to be visible. `list:<name>` says which curated roster
    # vouched for the account; `RETWEET of @x` says the account amplified rather than
    # reported, which is weaker evidence for a claim but a real signal about what a trusted
    # roster is attending to. Weigh it; do not treat it as equivalent to first-hand reporting.
    if sig.get("list_label"):
        bits.append(f"list:{sig['list_label']}")
    if sig.get("is_retweet"):
        bits.append(f"RETWEET of @{sig.get('retweet_of') or '?'}")
    evidence = item.get("evidence", []) or []
    url = evidence[0].get("url", "") if evidence else ""
    pillars = ",".join(item.get("pillars", [])) or "-"
    scope = ",".join(item.get("scope", [])[:3]) or "-"
    related = item.get("related", [])
    rel = f"  +[{', '.join(related[:4])}]" if related else ""
    # rake may have grounded this item (read the source): show its synopsis so the
    # model triages the real story, not an abstract t0 label.
    synopsis = sig.get("synopsis")
    syn = f"\n      ↳ {str(synopsis)[:160]}" if synopsis else ""
    return (
        f"[{item.get('id', '?')}] {item.get('label', '')[:70]} "
        f"| {item.get('channel', '?')}/{item.get('kind', '?')} "
        f"| pillars={pillars} scope={scope} | {' '.join(bits)} "
        f"| {len(evidence)} urls {url[:60]}{rel}{syn}"
    )


_DIRECTIVE = (
    "TASK: Turn the t0 pool above into a research-vector portfolio (t1) with BROAD "
    "coverage and GENUINE SPECTRUM. Drop only genuine non-news/spam. A single hit "
    "that's its own story is its own vector (the common case); fuse hits into one "
    "vector only when they're genuinely the same story or one pattern — never merge "
    "distinct stories to look synthesized. "
    "X BAND: when an X hit is a real development (not empty engagement bait), give it "
    "its own vector with primary supporting_hit from channel x — do not only absorb X "
    "into Iran/Fed/macro mega-vectors. Aim for about {target} vectors (operator "
    "target) — more if the pool truly has more real stories, fewer only if the pool "
    "is thin. Prefer covering near that size over pruning to a short highlight reel; "
    "long tail as 'light'. "
    "Double-click free-first; use source=x when a live X-native strand is missing from "
    "wires. Return a broad, effort-tiered ResearchPortfolio; cite supporting t0 hit ids."
)


def _directive() -> str:
    from algent_backend.agent_system.agents.newsroom.flags import synthesis_target_vectors
    return _DIRECTIVE.format(target=synthesis_target_vectors())
