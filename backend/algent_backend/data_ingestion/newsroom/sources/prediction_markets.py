"""
Prediction markets as a discovery channel — Polymarket (free, no key).

A novel signal most news pipelines ignore: an active, high-volume, or moving
market *is itself* a story lead. "X is priced at 30% vs Y at 70%" signals a live
dynamic worth reporting, and the odds are an immediate, citable detail. This is a
forward-looking complement to GKG's backward-looking article index.

We pull active markets, drop the sports/parlay noise (volume there is huge but
not news), and normalize each to a small record. The "signal" for v1 is reach
(volume + liquidity); a moving-odds signal (price change vs a prior snapshot) is
a natural follow-up using the same rolling-memory trick as GKG velocity.

Free Gamma API, single GET. Kalshi is a planned second source (its market data is
free too, but pricing needs a second call).
"""

from __future__ import annotations

import json
from typing import Any

from algent_backend.data_ingestion.newsroom.topic_filters import is_sports_text

_GAMMA_MARKETS = "https://gamma-api.polymarket.com/markets"
_TIMEOUT_S = 20.0
_HEADERS = {"User-Agent": "Algent/0.1 (news discovery ingestion)"}

# Extra market-shape markers (shared sports list is primary).
_MARKET_SPORTS_EXTRA: tuple[str, ...] = (
    "play for the", "play in the", "to win the", "mvp", "championship game",
    "wc champions", "champions photo", "score the most", "points in the",
)


def fetch_polymarket(*, limit: int = 30, scan: int = 250, client: object | None = None) -> list[dict[str, Any]]:
    """Top active non-sports markets by *recent* (24h) activity, normalized.

    Ranked by 24h volume, not total — total surfaces perennial long-shots, while
    recent activity surfaces what's being bet on *now* (the live signal).
    """
    import httpx

    own = client is None
    http = client or httpx.Client(timeout=_TIMEOUT_S, headers=_HEADERS)
    try:
        response = http.get(  # type: ignore[attr-defined]
            _GAMMA_MARKETS,
            params={"closed": "false", "active": "true", "limit": scan,
                    "order": "volume24hr", "ascending": "false"},
        )
        if response.status_code != 200:
            raise RuntimeError(f"Polymarket fetch failed: HTTP {response.status_code}")
        raw = response.json()
    finally:
        if own:
            http.close()  # type: ignore[attr-defined]

    markets = raw if isinstance(raw, list) else raw.get("data", [])
    out: list[dict[str, Any]] = []
    for market in markets:
        record = _normalize(market)
        if record is not None and not _is_sports(record["question"]):
            out.append(record)
            if len(out) >= limit:
                break
    return out


def _normalize(market: dict[str, Any]) -> dict[str, Any] | None:
    question = (market.get("question") or "").strip()
    if not question:
        return None
    return {
        "question": question,
        "outcomes": _loads(market.get("outcomes")),
        "prices": _loads(market.get("outcomePrices")),
        "last_price": _num(market.get("lastTradePrice")),
        # The "something's happening" signals: recent trading + odds movement.
        "volume_24h": _num(market.get("volume24hr")),
        "price_change_1d": _num(market.get("oneDayPriceChange")),
        "liquidity": _num(market.get("liquidity")),
        "end_date": market.get("endDate", ""),
        "url": f"https://polymarket.com/event/{market.get('slug', '')}",
        "source": "polymarket",
    }


def _is_sports(question: str) -> bool:
    if is_sports_text(question):
        return True
    q = question.casefold()
    return any(marker in q for marker in _MARKET_SPORTS_EXTRA)


def _loads(value: object) -> list:
    """Gamma returns outcomes/prices as JSON strings; parse defensively."""
    if isinstance(value, list):
        return value
    try:
        return json.loads(value) if value else []
    except (ValueError, TypeError):
        return []


def _num(value: object) -> float:
    try:
        return round(float(value), 2)
    except (ValueError, TypeError):
        return 0.0
