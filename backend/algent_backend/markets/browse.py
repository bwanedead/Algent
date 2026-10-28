"""
Market browsing for the day book: live, keyless Polymarket (Gamma events and markets, CLOB price history) plus our own mirror. Read-only.

The agent is handed no list. ``search`` finds markets that resolve inside a window (default ``flags.DAY_HORIZON_H`` hours) across every category the
blocklist allows (``flags.BLOCK_TAGS``), above the mirror's liquidity and volume floors; ``load`` is one market in full (rules, end, price, spread,
recent path). ``tradable_why`` is the one definition of "this market may be bought or sold", used by browsing and by order execution, so what the agent
is shown and what the book will fill cannot drift apart.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from typing import Any

from . import flags, polymarket, store
from .contracts import Market
from .polymarket import CLOB, GAMMA, Fetch

_WORD = re.compile(r"[a-z0-9]{3,}")
EVENT_PAGES = 2                      # window sweeps: this many pages of 100 events, busiest first


@dataclass
class View:
    """One market as the agent sees it: our Market record, the raw Gamma row, the price and the book's spread."""

    market: Market
    raw: dict[str, Any]
    yes: float | None
    bid: float | None = None
    ask: float | None = None
    path: list[tuple[str, float]] = field(default_factory=list)
    depth: dict[str, float] = field(default_factory=dict)         # CLOB book: best bid / ask and the dollars resting within DEPTH_BAND of each
    source: str = "live"

    @property
    def spread(self) -> float | None:
        return round(self.ask - self.bid, 4) if self.bid is not None and self.ask is not None and self.ask >= self.bid else None

    def hours_left(self, now: datetime) -> float | None:
        end = store.parse_iso(self.market.end_date)
        return round((end - now).total_seconds() / 3600, 1) if end else None


def _tokens(text: str) -> set[str]:
    return set(_WORD.findall(text.lower()))


def view_of(raw: dict[str, Any], event: dict[str, Any] | None = None) -> View | None:
    m = polymarket.parse_market(raw, event)
    if m is None:
        return None
    return View(m, raw, polymarket.yes_price(raw), polymarket.num(raw.get("bestBid")), polymarket.num(raw.get("bestAsk")))


def tradable_why(v: View, now: datetime, *, min_liquidity: float | None = None, horizon_h: float | None = None, min_hours: float | None = None) -> str:
    """Why this market may NOT be traded now ('' when it may): closed, blocked category, outside the window, too thin, or no price."""
    raw, m = v.raw, v.market
    if raw.get("closed") or raw.get("active") is False or raw.get("archived"):
        return "the market is closed to trading"
    if set(m.tags) & set(flags.BLOCK_TAGS):
        return "its category is on the blocklist (" + ", ".join(sorted(set(m.tags) & set(flags.BLOCK_TAGS))[:3]) + ")"
    hours = v.hours_left(now)
    lo = flags.DAY_MIN_HOURS_LEFT if min_hours is None else min_hours          # a roster strategy passes its own window; the default is the day book's
    hi = flags.DAY_HORIZON_H if horizon_h is None else horizon_h
    if hours is None:
        return "it has no end time"
    if hours < lo:
        return f"it ends in {max(hours, 0):.1f} h, inside the {lo:g} h cut-off"
    if hours > hi:
        return f"it ends in {hours:.0f} h, beyond the {hi:g} h horizon"
    if m.liquidity < (flags.MIN_LIQUIDITY_USD if min_liquidity is None else min_liquidity) or m.volume < flags.MIN_VOLUME_USD:
        return f"too thin (liquidity ${m.liquidity:,.0f}, volume ${m.volume:,.0f})"
    if v.yes is None:
        return "no price"
    return ""


def _event_views(events: list[dict[str, Any]]) -> list[View]:
    out = []
    for ev in events:
        for raw in ev.get("markets") or []:
            if isinstance(raw, dict) and (v := view_of(raw, ev)) is not None:
                out.append(v)
    return out


def _window_events(now: datetime, hours: float, get: Fetch, min_hours: float | None = None) -> list[dict[str, Any]]:
    """Open events with an end date inside the window, busiest first (Gamma filters on the EVENT's end; a market is checked again on its own)."""
    lo, hi = now + timedelta(hours=flags.DAY_MIN_HOURS_LEFT if min_hours is None else min_hours), now + timedelta(hours=hours)
    out: list[dict[str, Any]] = []
    for page in range(EVENT_PAGES):
        data = get(f"{GAMMA}/events", {"active": "true", "closed": "false", "end_date_min": lo.strftime("%Y-%m-%dT%H:%M:%SZ"),
                                       "end_date_max": hi.strftime("%Y-%m-%dT%H:%M:%SZ"), "order": "volume24hr", "ascending": "false", "limit": 100, "offset": page * 100})
        rows = [e for e in data if isinstance(e, dict)] if isinstance(data, list) else []
        out += rows
        if len(rows) < 100:
            break
    return out


def _text_search(query: str, get: Fetch) -> list[dict[str, Any]]:
    data = get(f"{GAMMA}/public-search", {"q": query, "events_status": "active", "limit_per_type": 20})
    return [e for e in (data.get("events") if isinstance(data, dict) else None) or [] if isinstance(e, dict)]


def _mirror_views(now: datetime) -> list[View]:
    """Open markets of our own mirror, priced from their newest live snapshot (a fallback door: the live sweep is the first)."""
    prices = store.snapshots_by_market()
    out = []
    for m in store.markets().values():
        live = [s for s in prices.get(m.id, []) if s.source == "live"]
        if m.status == "open" and live and (store.parse_iso(live[-1].at) or now) >= now - timedelta(hours=flags.PRICE_FRESH_H):
            out.append(View(m, {}, live[-1].p, live[-1].bid, live[-1].ask, source="mirror"))
    return out


def search(query: str, *, now: datetime, get: Fetch, ends_within_h: float | None = None, min_liquidity: float | None = None, limit: int | None = None,
           horizon_h: float | None = None, min_hours: float | None = None) -> list[View]:
    """Markets resolving inside the window, relevance first when there is a query (else busiest first). Every row passes ``tradable_why``."""
    ceiling = float(flags.DAY_HORIZON_H if horizon_h is None else horizon_h)
    hours = min(float(ends_within_h or ceiling), ceiling)
    limit = max(1, min(int(limit or flags.DAY_SEARCH_LIMIT), flags.DAY_SEARCH_LIMIT_MAX))
    want = _tokens(query or "")
    events = _window_events(now, hours, get, min_hours)
    if want:
        try:
            events = _text_search(query, get) + events
        except Exception:  # noqa: BLE001 - the window sweep still answers
            pass
    found: dict[str, View] = {}
    for v in [*_event_views(events), *_mirror_views(now)]:
        if v.market.id in found:
            continue
        hrs = v.hours_left(now)
        if hrs is None or hrs > hours or tradable_why(v, now, min_liquidity=min_liquidity, horizon_h=ceiling, min_hours=min_hours):
            continue
        found[v.market.id] = v
    def score(v: View) -> int:
        return len(want & _tokens(f"{v.market.question} {v.market.event_title} {' '.join(v.market.tags)}")) if want else 0
    rows = [v for v in found.values() if score(v) or not want]
    return sorted(rows, key=lambda v: (-score(v), -v.market.volume))[:limit]


def path_of(token_yes: str, market_id: str, get: Fetch) -> list[tuple[str, float]]:
    """Recent YES prices from the CLOB (hourly over ``DAY_PATH_HOURS``), thinned to ``DAY_PATH_POINTS``."""
    if not token_yes:
        return []
    data = get(f"{CLOB}/prices-history", {"market": token_yes, "interval": "1d", "fidelity": 60})
    pts = []
    for r in (data.get("history") if isinstance(data, dict) else None) or []:
        t, p = polymarket.num(r.get("t")), polymarket.num(r.get("p"))
        if t is not None and p is not None:
            pts.append((datetime.fromtimestamp(t, UTC).strftime("%m-%d %H:%MZ"), round(p, 4)))
    step = max(1, -(-len(pts) // flags.DAY_PATH_POINTS))
    return pts[::step][-flags.DAY_PATH_POINTS:]


DEPTH_BAND = 0.05


def depth_of(token_yes: str, get: Fetch) -> dict[str, float]:
    """The YES token's order book from the CLOB: best bid and ask and the dollars resting within ``DEPTH_BAND`` of each. Empty when it is not exposed."""
    if not token_yes:
        return {}
    data = get(f"{CLOB}/book", {"token_id": token_yes})
    if not isinstance(data, dict):
        return {}

    def levels(key: str) -> list[tuple[float, float]]:
        out = []
        for r in data.get(key) or []:
            p, z = polymarket.num(r.get("price")), polymarket.num(r.get("size"))
            if p is not None and z is not None:
                out.append((p, z))
        return out

    bids, asks = levels("bids"), levels("asks")
    out: dict[str, float] = {}
    if bids:
        bb = max(p for p, _ in bids)
        out.update(bid=bb, bid_depth_usd=round(sum(p * z for p, z in bids if p >= bb - DEPTH_BAND), 2))
    if asks:
        ba = min(p for p, _ in asks)
        out.update(ask=ba, ask_depth_usd=round(sum(p * z for p, z in asks if p <= ba + DEPTH_BAND), 2))
    return out


def load(market_id: str, *, get: Fetch, with_path: bool = False) -> View | None:
    """One market, fresh from Gamma (tags come from its event when the market row lacks them). None if Gamma does not know it."""
    raw = polymarket.market_by_id(str(market_id).strip(), get)
    if raw is None:
        return None
    ev = ((raw.get("events") or [{}])[0]) or {}
    if not ev.get("tags") and ev.get("id"):
        try:
            full = get(f"{GAMMA}/events/{ev['id']}", None)
            ev = full if isinstance(full, dict) and full.get("id") else ev
        except Exception:  # noqa: BLE001 - tags unknown: the blocklist check then relies on the market row alone
            pass
    v = view_of(raw, ev)
    if v is not None and with_path:
        try:
            v.path = path_of(v.market.token_yes, v.market.id, get)
        except Exception:  # noqa: BLE001 - a path is context, never a reason to refuse
            v.path = []
        try:
            v.depth = depth_of(v.market.token_yes, get)
            v.bid, v.ask = v.depth.get("bid", v.bid), v.depth.get("ask", v.ask)
        except Exception:  # noqa: BLE001 - depth is context too
            v.depth = {}
    return v


def row(v: View, now: datetime) -> dict[str, Any]:
    return {"id": v.market.id, "question": v.market.question, "event": v.market.event_title, "ends": v.market.end_date[:16] + "Z", "hours_left": v.hours_left(now),
            "yes": v.yes, "spread": v.spread, "liquidity": round(v.market.liquidity), "volume": round(v.market.volume), "source": v.source}


def dump(v: View, now: datetime) -> str:
    """The `market(id)` answer: everything a trader reads before an order."""
    m = v.market
    why = tradable_why(v, now)
    lines = [f"{m.id}: {m.question}", f"event: {m.event_title}", f"ends: {m.end_date[:16]}Z ({v.hours_left(now)} h left)",
             f"YES {v.yes}  NO {None if v.yes is None else round(1 - v.yes, 4)}  bid {v.bid}  ask {v.ask}  spread {v.spread}",
             f"liquidity ${m.liquidity:,.0f}  volume ${m.volume:,.0f}  tags {', '.join(m.tags[:6]) or 'unknown'}",
             "tradable: " + ("yes" if not why else f"NO, {why}"), "rules: " + (m.description or "(none given)")]
    if v.depth:
        lines.append(f"book: bid {v.depth.get('bid')} (${v.depth.get('bid_depth_usd', 0):,.0f} within {DEPTH_BAND:.0%}), "
                     f"ask {v.depth.get('ask')} (${v.depth.get('ask_depth_usd', 0):,.0f} within {DEPTH_BAND:.0%})")
    if v.path:
        lines.append("YES path: " + " ".join(f"{t} {p}" for t, p in v.path))
    return "\n".join(lines)


def to_json(rows: list[dict[str, Any]]) -> str:
    return json.dumps(rows, separators=(",", ":"))
