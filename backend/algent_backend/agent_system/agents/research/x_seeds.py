"""
Hydrate research vectors with X post URLs from t0 supporting hits.

Discovery often promotes X-primary hits (``x:x_news:…``, ``x:x_novelty:…``) while
synthesis fills ``sources`` with wire URLs. Research then never sees the first-party
post. This module restores X URLs so the profile agent can deep-read them and run
``web_search(source="x")`` with footing — without inventing posts.
"""

from __future__ import annotations

from typing import Any

_X_HOST_MARKERS = ("x.com/", "twitter.com/")


def is_x_url(url: str) -> bool:
    u = (url or "").lower()
    return any(m in u for m in _X_HOST_MARKERS)


def x_url_from_hit_id(hit_id: str) -> str | None:
    """Best-effort status URL from a t0 X item id (``x:x_news:123…``)."""
    parts = str(hit_id or "").split(":")
    if len(parts) < 3 or parts[0] != "x":
        return None
    status_id = parts[-1]
    if not status_id.isdigit():
        return None
    return f"https://x.com/i/web/status/{status_id}"


def collect_x_urls_from_pool_item(item: dict[str, Any]) -> list[str]:
    urls: list[str] = []
    for ev in item.get("evidence") or []:
        if isinstance(ev, dict):
            u = str(ev.get("url") or "")
        else:
            u = str(getattr(ev, "url", "") or "")
        if is_x_url(u) and u not in urls:
            urls.append(u)
    return urls


def hydrate_vector_with_x_seeds(
    vector: dict[str, Any],
    pool: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Return a copy of ``vector`` with X seed URLs prepended to ``sources``.

    Also sets ``x_seed_urls`` (list) for the research message band.
    """
    v = dict(vector)
    sources = [str(s) for s in (v.get("sources") or []) if s]
    seen = set(sources)
    x_seeds: list[str] = []

    items_by_id: dict[str, dict[str, Any]] = {}
    if pool:
        for item in pool.get("items") or []:
            if isinstance(item, dict) and item.get("id"):
                items_by_id[str(item["id"])] = item

    for hid in v.get("supporting_hits") or []:
        hid_s = str(hid)
        item = items_by_id.get(hid_s)
        urls: list[str] = []
        if item:
            urls = collect_x_urls_from_pool_item(item)
        if not urls and (hid_s.startswith("x:") or "x_news" in hid_s or "x_novelty" in hid_s):
            reconstructed = x_url_from_hit_id(hid_s)
            if reconstructed:
                urls = [reconstructed]
        for u in urls:
            if u not in seen:
                sources.insert(0, u)
                seen.add(u)
            if u not in x_seeds:
                x_seeds.append(u)

    # Also promote any x.com already in sources into the seed list (order preserved).
    for s in list(sources):
        if is_x_url(s) and s not in x_seeds:
            x_seeds.append(s)

    v["sources"] = sources
    v["x_seed_urls"] = x_seeds
    v["x_primary"] = bool(x_seeds) or any(
        str(h).startswith("x:") for h in (v.get("supporting_hits") or [])
    )
    return v


def hydrate_portfolio_vectors(
    portfolio: dict[str, Any],
    pool: dict[str, Any] | None,
) -> dict[str, Any]:
    """Hydrate every vector in a portfolio dict (synthesis post-pass)."""
    if not portfolio or not portfolio.get("vectors"):
        return portfolio
    out = dict(portfolio)
    out["vectors"] = [
        hydrate_vector_with_x_seeds(dict(v), pool) for v in portfolio["vectors"]
    ]
    return out
