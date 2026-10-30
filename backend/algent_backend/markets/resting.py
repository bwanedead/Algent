"""
RESTING LIMIT ORDERS for the paper bots. PAPER ONLY: nothing here can reach a venue.

A bot that has a price in mind ("my probability makes YES worth buying at 40c or less") leaves a limit order instead of waiting for its next run. The order is a
record (``contracts.RestingOrder``) in ``resting_orders.jsonl``; a FREE pass (no model call) fills it between runs, through the same ``guards.apply`` and the same
``Decision`` ledger an immediate order uses, so a resting fill is an ordinary fill in every book calculation (cash, holdings, realised P&L, the per-day fill minimum).

    place(...)    validate like an immediate order (the position and exposure caps at placement; open-order and expiry limits) and write the order ``open``
    cancel(...)   the bot withdraws an open order (a new line, ``cancelled``)
    run_pass(...) for every open order: expire it (past ``expires_at`` or the market closed), else, against a price snapshot that is fresh enough, fill it when the
                  all-in price on its side is at or better than its limit. The caps are checked AGAIN at the fill (cash and holdings may have moved): a fill the
                  guards block outright becomes ``cancelled`` with their reason; one they merely trim fills smaller, exactly as an immediate order would.

The record is append-only: every transition is a new line carrying the whole order, so nothing is rewritten and each expiry or cancellation is on file with its reason.
The LIMIT is the all-in price on the order's own side, slippage included: a buy fills while ``side price + SLIPPAGE`` is at or below it, a sell while
``side price - SLIPPAGE`` is at or above it. The fill price is the same all-in price the guards compute at that moment (equal to the limit or better).
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Any

from . import book, flags, guards, polymarket, store, strategies
from .contracts import Decision, RestingOrder, decision_id, resting_id
from .polymarket import Fetch

EPS = 1e-9


def _iso(t: datetime) -> str:
    return t.isoformat(timespec="seconds")


# ── the record ───────────────────────────────────────────────────────────────────────────────────
def orders(book_id: str | None = None) -> dict[str, RestingOrder]:
    """The state of every order (the last line per id), keyed by id, oldest placement first."""
    last: dict[str, RestingOrder] = {}
    for r in store.resting_events(book_id):
        last[r.id] = r
    return dict(sorted(last.items(), key=lambda kv: kv[1].placed_at))


def open_orders(book_id: str) -> list[RestingOrder]:
    return [o for o in orders(book_id).values() if o.status == "open"]


def _move(o: RestingOrder, status: str, now: datetime, note: str = "", fill_id: str = "") -> RestingOrder:
    return o.model_copy(update={"status": status, "at": _iso(now), "note": note[:300], "fill_id": fill_id, "filled_at": _iso(now) if status == "filled" else ""})


def fill_price(action: str, yes: float) -> float:
    """The all-in price an order of this kind would pay now (buy: quote plus slippage; sell: quote minus slippage); the number a limit is compared with."""
    if action == "sell":
        raise ValueError("a sell's price depends on the side held: use sell_price")
    side = "yes" if action == "buy_yes" else "no"
    return round(min(0.99, book.side_price(yes, side) + flags.SLIPPAGE), 4)


def sell_price(side: str, yes: float) -> float:
    return round(max(0.01, book.side_price(yes, side) - flags.SLIPPAGE), 4)


# ── placing and cancelling (the bot's tools call these) ──────────────────────────────────────────
def place(st: strategies.Strategy, ds: list[Decision], *, now: datetime, market_id: str, end: datetime | None, yes: float, way: str, side: str, limit: float, usd: float,
          fraction: float, p_yes: float, hours: float, reason: str) -> tuple[RestingOrder | None, str]:
    """Validate and record one resting order. Returns ``(order, message)``; no order means the message is the refusal. The checks mirror an immediate order's:
    the same position and exposure caps (evaluated now, and again at the fill), plus an open-order cap per book and a required, capped expiry."""
    if not flags.RESTING_ENABLED:
        return None, "resting orders are switched off (markets/flags RESTING_ENABLED)"
    if way not in ("buy", "sell"):
        return None, "way must be buy or sell"
    if way == "buy" and side not in ("yes", "no"):
        return None, "a resting buy needs side yes or no"
    if not 0.0 < p_yes < 1.0:
        return None, "give p_yes: your probability that the market resolves YES (between 0 and 1); it is recorded with the order"
    if not 0.01 <= limit <= 0.99:
        return None, "limit is the all-in price per share on your side, between 0.01 and 0.99"
    if hours <= 0:
        return None, "an expiry is required: hours is how long the order may rest"
    if end is None or end <= now:
        return None, "the market has no future end time"
    mine = open_orders(st.id)
    if len(mine) >= flags.RESTING_MAX_OPEN:
        return None, f"you already have {len(mine)} open resting orders (the limit is {flags.RESTING_MAX_OPEN}); cancel one first"
    action = "sell" if way == "sell" else f"buy_{side}"
    twin = next((o for o in mine if o.market_id == market_id and o.action == action), None)
    if twin is not None:
        return None, f"you already have an open resting {action.replace('_', ' ')} on this market [{twin.id}]; cancel it first to change it"
    held = book.holdings(ds).get(market_id)
    exposure = sum(h.cost for h in book.holdings(ds).values())
    clips: list[str] = []
    if way == "buy":
        if fill_price(action, yes) <= limit + EPS:
            return None, f"the price already reaches your limit ({fill_price(action, yes):.3f} all-in now): use buy to fill it at once"
        g = guards.apply(action, max(0.0, usd), held=held, yes_price=yes, cash=book.cash(ds), exposure=exposure, tradable=True, position_frac=st.position_frac,
                         exposure_frac=st.exposure_frac, bankroll=st.bankroll)
        if g.action == "hold":
            return None, "would be refused by the book's limits: " + "; ".join(g.clips)
        usd, clips = round(-g.cash_flow, 2), g.clips
    else:
        if held is None:
            return None, "no position to sell on this market"
        if sell_price(held.side, yes) >= limit - EPS:
            return None, f"the price already reaches your limit ({sell_price(held.side, yes):.3f} all-in now): use sell to fill it at once"
        usd = 0.0
        fraction = 1.0 if not 0.0 < fraction < 1.0 else round(fraction, 4)
    expires = min(now + timedelta(hours=min(hours, flags.RESTING_MAX_HOURS)), end)
    o = RestingOrder(id=resting_id(st.id, market_id, action, _iso(now)), book=st.id, market_id=market_id, action=action, limit_price=round(limit, 4),  # type: ignore[arg-type]
                     usd=usd, fraction=fraction if way == "sell" else 0.0, p_yes=round(p_yes, 4), reason=" ".join(reason.split())[:420], placed_at=_iso(now),
                     expires_at=_iso(expires), at=_iso(now))
    store.append_resting([o])
    size = f"${usd:,.2f}" if way == "buy" else f"{fraction:.0%} of the position"
    capped = f" (expiry capped at {expires.strftime('%Y-%m-%d %H:%MZ')})" if expires < now + timedelta(hours=hours) else ""
    trimmed = f" Trimmed: {'; '.join(clips)}." if clips else ""
    return o, (f"RESTING order [{o.id}] placed: {action.replace('_', ' ')} {size} at {limit:.3f} all-in or better, until {o.expires_at[:16]}Z{capped}. It fills by itself between "
               f"your runs if the price reaches it (the limits are checked again then), else expires.{trimmed}")


def cancel(book_id: str, ref: str, now: datetime, note: str = "") -> str:
    o = next((x for x in open_orders(book_id) if x.id == ref.strip()), None)
    if o is None:
        return f"no open resting order {ref!r} (see the RESTING ORDERS lines of your portfolio)"
    store.append_resting([_move(o, "cancelled", now, "cancelled by the bot" + (f": {' '.join(note.split())[:200]}" if note.strip() else ""))])
    return f"CANCELLED resting order [{o.id}]"


# ── the free fill pass ───────────────────────────────────────────────────────────────────────────
def _refresh_quotes(ids: set[str], get: Fetch, now: datetime, errors: dict[str, str]) -> set[str]:
    """Fetch the live quote of each market that carries an open order and write a snapshot (these markets only, so the extra lines are few). Returns the ids that
    are now closed to trading. A failed fetch leaves the market without a fresh snapshot, which the fill step then skips."""
    closed: set[str] = set()
    at = _iso(now)
    snaps = []
    for mid in sorted(ids):
        try:
            raw = polymarket.market_by_id(mid, get)
        except Exception as exc:  # noqa: BLE001 - one market down must not stop the others
            errors[mid] = f"{type(exc).__name__}: {str(exc)[:120]}"
            continue
        if raw is None:
            continue
        if raw.get("closed") or raw.get("active") is False:
            closed.add(mid)
        if (s := polymarket.snapshot_of(raw, mid, at)) is not None:
            snaps.append(s)
    store.append_snapshots(snaps)
    return closed


def run_pass(*, now: datetime | None = None, get: Fetch | None = None, refresh: bool = True) -> dict[str, Any]:
    """The free fill pass: refresh the quotes of the markets with open orders, then expire / fill / cancel each open order. No model call. ``refresh=False`` uses only
    the snapshots on file (the tests do; the schedule never does)."""
    now = now or datetime.now(UTC)
    out: dict[str, Any] = {"as_of": _iso(now), "open": 0, "filled": 0, "expired": 0, "cancelled": 0, "skipped_stale": 0, "errors": {}}
    open_ = [o for o in orders().values() if o.status == "open"]
    out["open"] = len(open_)
    if not open_:
        return out
    closed: set[str] = set()
    if refresh:
        from algent_backend import polite_http

        if get is None:
            polite_http.clear_memo()
        closed = _refresh_quotes({o.market_id for o in open_}, get or polymarket.fetch, now, out["errors"])
    ms, prices = store.markets(), store.snapshots_by_market()
    for o in open_:                                           # oldest placement first
        verdict = _decide(o, now, ms, prices, closed)
        if verdict == "stale":
            out["skipped_stale"] += 1
        elif verdict in ("filled", "expired", "cancelled"):
            out[verdict] += 1
    out["open"] -= out["filled"] + out["expired"] + out["cancelled"]
    return out


def _decide(o: RestingOrder, now: datetime, ms: dict, prices: dict, closed: set[str]) -> str:
    """One open order against the latest price: writes its transition (if any) and returns it, or "open" / "stale" / "off" when it stays open."""
    m = ms.get(o.market_id)
    end = store.parse_iso(m.end_date) if m else None
    expiry = store.parse_iso(o.expires_at)
    if expiry is None or now >= expiry:
        store.append_resting([_move(o, "expired", now, "reached its expiry without the price reaching the limit")])
        return "expired"
    if m is None or m.status != "open" or o.market_id in closed or (end is not None and now >= end):
        store.append_resting([_move(o, "expired", now, "the market closed before the price reached the limit")])
        return "expired"
    try:
        st = strategies.get(o.book)
    except KeyError:
        return "off"
    if not (flags.RESTING_ENABLED and st.enabled):
        return "off"                                          # switched off: it neither fills nor is cancelled; it will expire
    live = [s for s in prices.get(o.market_id, []) if s.source == "live"]
    snap = live[-1] if live else None
    t = store.parse_iso(snap.at) if snap else None
    placed = store.parse_iso(o.placed_at)
    if snap is None or t is None or placed is None or t <= placed or now - t > timedelta(hours=flags.RESTING_MAX_SNAPSHOT_AGE_H):
        return "stale"                                        # no price newer than the order, or too old to trust: wait for the next pass
    ds = store.decisions(o.book)                              # fresh each time: an earlier fill in this pass has moved cash and holdings
    held = book.holdings(ds).get(o.market_id)
    yes = snap.p
    if o.action == "sell":
        if held is None:
            store.append_resting([_move(o, "cancelled", now, "no position left to sell")])
            return "cancelled"
        if sell_price(held.side, yes) < o.limit_price - EPS:
            return "open"
        value = held.shares * sell_price(held.side, yes)
        requested = 1e12 if o.fraction >= 1.0 or o.fraction <= 0.0 else o.fraction * value
    else:
        if fill_price(o.action, yes) > o.limit_price + EPS:
            return "open"
        hours = (end - now).total_seconds() / 3600 if end else 0.0
        if hours < st.min_hours_left:
            store.append_resting([_move(o, "cancelled", now, f"the market ends in {max(hours, 0):.1f} h, inside the {st.min_hours_left:g} h cut-off")])
            return "cancelled"
        requested = o.usd
    fill = guards.apply(o.action, requested, held=held, yes_price=yes, cash=book.cash(ds), exposure=sum(h.cost for h in book.holdings(ds).values()), tradable=True,
                        position_frac=st.position_frac, exposure_frac=st.exposure_frac, bankroll=st.bankroll)
    if fill.action == "hold":
        store.append_resting([_move(o, "cancelled", now, "blocked at the fill: " + "; ".join(fill.clips))])
        return "cancelled"
    at = _iso(now)
    d = Decision(id=decision_id(o.market_id, fill.action, f"{at}{o.book}{o.id}"), market_id=o.market_id, at=at, day=at[:10], action=fill.action,  # type: ignore[arg-type]
                 requested=round(min(requested, 1e9), 2), side=fill.side, price=fill.price, shares=fill.shares, cash_flow=fill.cash_flow, realised=fill.realised,  # type: ignore[arg-type]
                 rationale=o.reason, clips=fill.clips, ours=o.p_yes, market=yes, model="resting", prompt_version=st.prompt_version, book=o.book, tag="resting", order_id=o.id,
                 hours_to_end=round((end - now).total_seconds() / 3600, 1) if end else None)
    store.append_decisions([d])
    store.append_resting([_move(o, "filled", now, f"filled at {fill.price:.3f} against a snapshot of {snap.at[:16]}Z (limit {o.limit_price:.3f})", d.id)])
    return "filled"


# ── what the page shows ──────────────────────────────────────────────────────────────────────────
def section(book_id: str) -> dict[str, Any]:
    """One book's part of the published document: its open orders (with the live price on their side) and its most recent resting fills."""
    ms, prices = store.markets(), store.snapshots_by_market()
    held = book.holdings(store.decisions(book_id))
    rows = []
    for o in open_orders(book_id):
        m = ms.get(o.market_id)
        p = book.last_price(prices.get(o.market_id, []))
        side = o.action.removeprefix("buy_") if o.action != "sell" else (held[o.market_id].side if o.market_id in held else "")
        rows.append({"id": o.id, "market_id": o.market_id, "question": m.question if m else o.market_id, "url": m.url if m else "", "action": o.action, "side": side,
                     "limit": o.limit_price, "usd": o.usd, "fraction": o.fraction, "now": None if p is None or not side else round(book.side_price(p, side), 4),
                     "p_yes": o.p_yes, "reason": o.reason, "placed_at": o.placed_at, "expires_at": o.expires_at})
    fills = [{"id": d.id, "order_id": d.order_id, "market_id": d.market_id, "question": (ms[d.market_id].question if d.market_id in ms else d.market_id), "action": d.action,
              "side": d.side, "price": d.price, "stake": round(abs(d.cash_flow), 2), "at": d.at}
             for d in sorted(store.decisions(book_id), key=lambda d: d.at, reverse=True) if d.tag == "resting" and d.action != "hold"][:flags.RESTING_FILLS_SHOWN]
    return {"open": rows, "fills": fills}
