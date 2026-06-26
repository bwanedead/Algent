"""
The rake chunk message — one chunk of t0 items rendered for the scout to verdict.

Compact, id-forward: each line leads with the item id (the scout must echo it in
its verdict), then the label and the free signals it can judge from without a tool
call. Mirrors the synthesis t0 rendering but trimmed to what a keep/toss needs.
"""

from __future__ import annotations

from typing import Any


def build_chunk_message(items: list[dict[str, Any]]) -> str:
    """Render a chunk of pool-item dicts into the scout's task message."""
    lines = [
        "# RAKE CHUNK — keep or toss each item below",
        f"items in this chunk: {len(items)}",
        "",
        "Each line: [id] label | channel/kind | pillars | signals | evidence-url",
        "",
    ]
    lines.extend(_fmt_item(item) for item in items)
    lines.extend(["", _DIRECTIVE])
    return "\n".join(lines)


def _fmt_item(item: dict[str, Any]) -> str:
    sig = item.get("signals", {}) or {}
    bits = []
    for key in ("velocity", "rising", "novel", "language_count", "count", "volume_24h", "lane"):
        if sig.get(key) not in (None, False, ""):
            bits.append(f"{key}={sig[key]}")
    evidence = item.get("evidence", []) or []
    url = evidence[0].get("url", "") if evidence else ""
    pillars = ",".join(item.get("pillars", [])) or "-"
    return (
        f"[{item.get('id', '?')}] {item.get('label', '')[:70]} "
        f"| {item.get('channel', '?')}/{item.get('kind', '?')} "
        f"| pillars={pillars} | {' '.join(bits)} "
        f"| {len(evidence)} urls {url[:60]}"
    )


_DIRECTIVE = (
    "TASK: Return a RakeChunkResult with one verdict per id above — keep=true for a "
    "real newsworthy lead, keep=false for ads/spam/boilerplate/non-news/trivia. When "
    "unsure, keep. Judge from the signals; do at most ONE light free check on a true "
    "fence-sitter. Echo each id exactly."
)
