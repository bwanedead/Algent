"""
Polymarket, read-only. Public endpoints, no key, no account:

    GET https://gamma-api.polymarket.com/events?tag_slug=&active=true&closed=false&order=volume24hr   events with their markets and tags
    GET https://gamma-api.polymarket.com/markets/{id}                                                 one market (used to see a resolution)
    GET https://clob.polymarket.com/prices-history?market=<yes token>&interval=max&fidelity=1440      daily price history of the YES token

There is deliberately no function here that writes anything to Polymarket: no order, no auth, no wallet. Only binary Yes/No markets
are kept. Parsing is separate from fetching so tests feed saved payloads; ``fetch`` is the one place that touches the network.
"""

from __future__ import annotations

import json
from collections.abc import Callable
from datetime import UTC, datetime
from typing import Any

from algent_backend import polite_http

from . import flags
from .contracts import Market, Snapshot

GAMMA = "https://gamma-api.polymarket.com"
CLOB = "https://clob.polymarket.com"
SITE = "https://polymarket.com/event/"

Fetch = Callable[[str, dict[str, Any] | None], Any]


def fetch(url: str, params: dict[str, Any] | None = None) -> Any:
    """GET and parse JSON (polite_http: retries, pacing). Raises ``polite_http.SourceError``."""
    body = polite_http.get(url, params, headers={"Accept": "application/json"})
    try:
        return json.loads(body)
    except ValueError as exc:
        raise polite_http.SourceError(f"{url}: not JSON ({exc})") from exc


def _json_list(v: Any) -> list[Any]:
    if isinstance(v, list):
        return v
    try:
        out = json.loads(v) if isinstance(v, str) else []
    except ValueError:
        return []
    return out if isinstance(out, list) else []


def num(v: Any) -> float | None:
    try:
        return float(v)
    except (TypeError, ValueError):
        return None


def yes_price(m: dict[str, Any]) -> float | None:
    """The YES price as a probability: the book's mid when both sides are quoted, else the last trade, else the listed price."""
    bid, ask = num(m.get("bestBid")), num(m.get("bestAsk"))
    if bid is not None and ask is not None and ask > 0 and ask >= bid and (ask - bid) <= 0.25:
        return round((bid + ask) / 2, 4)
    for v in (m.get("lastTradePrice"), (_json_list(m.get("outcomePrices")) or [None])[0]):
        if (p := num(v)) is not None and 0.0 <= p <= 1.0:
            return p
    return None


def is_binary(m: dict[str, Any]) -> bool:
    return [str(o).strip().lower() for o in _json_list(m.get("outcomes"))] == ["yes", "no"]


def parse_market(m: dict[str, Any], event: dict[str, Any] | None = None) -> Market | None:
    """A Market from a Gamma market dict (``event`` supplies tags, title and the page slug). None for non-binary or malformed rows."""
    if not isinstance(m, dict) or not m.get("id") or not m.get("question") or not is_binary(m):
        return None
    event = event or (m.get("events") or [{}])[0] or {}
    tokens = _json_list(m.get("clobTokenIds"))
    tags = [t.get("slug", "") for t in event.get("tags") or [] if isinstance(t, dict) and t.get("slug")]
    slug = event.get("slug") or m.get("slug") or ""
    return Market(id=str(m["id"]), event_id=str(event.get("id") or ""), event_title=str(event.get("title") or ""),
                  question=" ".join(str(m["question"]).split()), slug=str(m.get("slug") or ""), url=SITE + slug if slug else "",
                  description=" ".join(str(m.get("description") or "").split())[:700], tags=tags,
                  token_yes=str(tokens[0]) if tokens else "", end_date=str(m.get("endDate") or ""),
                  volume=num(m.get("volumeNum") or m.get("volume")) or 0.0, liquidity=num(m.get("liquidityNum") or m.get("liquidity")) or 0.0)


def snapshot_of(m: dict[str, Any], market_id: str, at: str) -> Snapshot | None:
    p = yes_price(m)
    if p is None:
        return None
    return Snapshot(market_id=market_id, at=at, p=p, bid=num(m.get("bestBid")), ask=num(m.get("bestAsk")), last=num(m.get("lastTradePrice")),
                    volume=num(m.get("volumeNum") or m.get("volume")) or 0.0)


def resolution(m: dict[str, Any]) -> tuple[str, str]:
    """(outcome, resolved_at) when the market has finally resolved: 'yes' / 'no' on a settled price, 'void' for a split or cancelled
    resolution; ('', '') while it is still trading or awaiting its resolution."""
    prices = _json_list(m.get("outcomePrices"))
    p = num(prices[0]) if prices else None
    final = str(m.get("umaResolutionStatus") or "").lower() == "resolved"
    if not m.get("closed") or p is None:
        return "", ""
    if p >= flags.RESOLVED_YES_AT:
        out = "yes"
    elif p <= flags.RESOLVED_NO_AT:
        out = "no"
    elif final:
        out = "void"
    else:
        return "", ""
    return out, str(m.get("closedTime") or m.get("updatedAt") or datetime.now(UTC).isoformat(timespec="seconds"))


def events_for_tag(tag: str, get: Fetch = fetch, *, limit: int | None = None) -> list[dict[str, Any]]:
    data = get(f"{GAMMA}/events", {"tag_slug": tag, "active": "true", "closed": "false", "limit": limit or flags.EVENTS_PER_TAG,
                                   "order": "volume24hr", "ascending": "false"})
    return [e for e in data if isinstance(e, dict)] if isinstance(data, list) else []


def market_by_id(market_id: str, get: Fetch = fetch) -> dict[str, Any] | None:
    data = get(f"{GAMMA}/markets/{market_id}", None)
    return data if isinstance(data, dict) and data.get("id") else None


def history(token_yes: str, market_id: str, get: Fetch = fetch) -> list[Snapshot]:
    """Daily YES prices over the market's life from the CLOB (empty for a market with no trades yet)."""
    if not token_yes:
        return []
    data = get(f"{CLOB}/prices-history", {"market": token_yes, "interval": "max", "fidelity": flags.HISTORY_FIDELITY_MIN})
    rows = data.get("history") if isinstance(data, dict) else None
    out = []
    for r in rows or []:
        t, p = num(r.get("t")), num(r.get("p"))
        if t is not None and p is not None and 0.0 <= p <= 1.0:
            out.append(Snapshot(market_id=market_id, at=datetime.fromtimestamp(t, UTC).isoformat(timespec="seconds"), p=p, source="history"))
    return out[-flags.HISTORY_MAX_POINTS:]
