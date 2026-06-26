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


def build_t0_message(pool: dict[str, Any]) -> str:
    """Render a t0 ``DiscoveryPool`` dict into the run's task message."""
    items = pool.get("items", [])[:_MAX_ITEMS]
    lines = [
        "# t0 DISCOVERY POOL (your input to triage)",
        f"items: {pool.get('item_count', len(items))}   "
        f"channels: {pool.get('by_channel', {})}   pillars: {pool.get('by_pillar', {})}",
        f"t0_ref: {pool.get('gkg_batch_id') or pool.get('generated_at', '?')}",
        "",
        "Each line is a candidate hit: [id] label | tags | signals | evidence.",
        "",
    ]
    lines.extend(_fmt_item(item) for item in items)
    lines.extend(["", _DIRECTIVE])
    return "\n".join(lines)


def _fmt_item(item: dict[str, Any]) -> str:
    sig = item.get("signals", {}) or {}
    bits = []
    for key in ("velocity", "rising", "novel", "language_count", "avg_tone", "count"):
        if sig.get(key) not in (None, False):
            bits.append(f"{key}={sig[key]}")
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
    "TASK: Triage the t0 pool above into a research-vector portfolio (t1). Drop "
    "non-news / low-importance / non-pipeline-worthy hits. Condense hits that are "
    "the same story/theme into one vector; keep separately-important ones as their "
    "own vectors; fuse related hits into a larger-force vector where that's the "
    "real story. Double-click only into promising hits, free-first (read their "
    "URLs, search) — escalate to a paid channel only when genuinely needed. Return "
    "a selective ResearchPortfolio; cite each vector's supporting t0 hit ids."
)
