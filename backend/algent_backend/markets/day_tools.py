"""
The day book's tools: what one run of the agent can DO, executed by us and logged. Browsing (``browse.py``), the corpus (``research.run_query``, with its
blindness filter), a filed research request (``gaps.py``) and two paper orders. Orders go through the SAME guards and ledger as the other books
(``guards.apply``, ``book.holdings``, ``Decision`` lines tagged ``book: "day"``); a clipped or refused order is answered to the agent with its reason and
recorded as a ledger line (a refused one is a ``hold`` carrying the reason in ``clips``). PAPER ONLY: nothing here can reach a venue.

A ``Session`` is one run's state: the ledger as it grows, what was browsed, queried and ordered, and the corpus ids shown (only those may be cited).
"""

from __future__ import annotations

import time
from datetime import datetime, timedelta
from typing import Any

from algent_backend.retrieval.docs import clip

from . import book, browse, day_report, flags, gaps, guards, research, resting, sizing, store, strategies
from .contracts import BotForecast, Decision, Snapshot, ToolEvent, WatchEvent, bot_forecast_id, day_run_id, decision_id
from .day_prompt import Call, ForecastOut
from .polymarket import Fetch, num

NL = "\n"
CORPUS_TOOLS =("entity", "about", "search", "timeline", "related", "series")


def _args(call: Call) -> dict[str, Any]:
    return {k: v for k, v in call.model_dump(exclude_defaults=True).items() if k != "tool"}


def _money(x: float) -> str:
    return f"{'-' if x < 0 else ''}${abs(x):,.2f}"


class Session:
    def __init__(self, *, now: datetime, get: Fetch, corpus: Any = None, ds: list[Decision] | None = None, strategy: strategies.Strategy | None = None) -> None:
        self.now, self.get, self.corpus = now, get, corpus
        self.sid = (strategy.id if strategy else "day")             # which roster strategy this run is: its book, window, caps and watchlist
        self.ds: list[Decision] = list(ds if ds is not None else store.decisions(self.sid))
        self.events: list[ToolEvent] = []
        self.considered: dict[str, dict[str, str]] = {}
        self.queries: list[str] = []
        self.orders: list[str] = []
        self.shown: set[str] = set()
        self.attempts = 0
        self.run_id = day_run_id(now.isoformat(timespec="seconds"))
        self.prices: dict[str, float] = {}                          # the YES price last seen for each market this run (a forecast is stamped with it)
        self.forecast_log: dict[str, BotForecast] = {}              # this run's own probabilities, one per market; written once at the end (flush_forecasts)

    @property
    def s(self) -> strategies.Strategy:
        """The strategy's entry, read afresh from the roster so a changed flag takes effect for the next call."""
        return strategies.get(self.sid)

    # ── the dispatcher ───────────────────────────────────────────────────────────────────────────
    def run(self, turn: int, call: Call) -> ToolEvent:
        t0 = time.monotonic()
        ok, ref = True, ""
        try:
            text, ref = getattr(self, "t_" + call.tool)(call)
        except Exception as exc:  # noqa: BLE001 - a failed tool is a result the agent reads, never a crash
            ok, text = False, f"error: {type(exc).__name__}: {str(exc)[:160]}"
        ev = ToolEvent(n=len(self.events) + 1, turn=turn, tool=call.tool, args=_args(call), result=clip(text, flags.DAY_RESULT_CHARS), ok=ok,
                       ms=int((time.monotonic() - t0) * 1000), market_id=call.market.strip(), ref=ref)
        self.events.append(ev)
        return ev

    def _see(self, v: browse.View) -> None:
        self.considered.setdefault(v.market.id, {"id": v.market.id, "question": v.market.question, "ends": v.market.end_date[:16]})
        if v.yes is not None:
            self.prices[v.market.id] = v.yes

    # ── forecasts: the feedback signal, separate from trading ───────────────────────────────────
    def exposure(self) -> float:
        return sum(h.cost for h in book.holdings(self.ds).values())

    def floor_gap(self) -> float:
        """Paper dollars still to put at risk to reach the activity floor (0 when met, or when what is left is under the minimum ticket and cannot be bought)."""
        gap = self.s.floor_pct * self.s.bankroll - self.exposure()
        return gap if gap >= flags.TRADE_MIN_TICKET else 0.0

    def _note_forecast(self, mid: str, p: float, *, confidence: str = "", reason: str = "") -> bool:
        price = self.prices.get(mid)
        if mid not in self.considered or price is None or not 0.0 < p < 1.0:
            return False
        end = store.parse_iso(self.considered[mid].get("ends", "") + ":00+00:00") if self.considered[mid].get("ends") else None
        if end is not None and end <= self.now:                                # an ended market's price already shows the answer: not a forecast
            return False
        at = (self.now + timedelta(seconds=len(self.forecast_log))).isoformat(timespec="seconds")
        self.forecast_log[mid] = BotForecast(id=bot_forecast_id(self.s.id, self.run_id, mid), strategy=self.s.id, run_id=self.run_id, market_id=mid, at=at, day=at[:10],
                                             p=round(min(flags.P_MAX, max(flags.P_MIN, p)), 4), market=price, confidence=confidence, question=self.considered[mid]["question"],
                                             reason=" ".join(reason.split())[:300])
        return True

    def forecasts(self, items: list[ForecastOut]) -> str:
        """Record the turn's forecasts. A market not yet seen this run is loaded once; one that cannot be priced is skipped and the answer says so.
        A p given as a fraction (0.07) rather than a percent is read as a fraction, never as 0.07%."""
        done, skipped = 0, []
        for f in items[:flags.FORECASTS_PER_TURN]:
            mid = f.market.strip()
            if mid not in self.prices:
                try:
                    v = browse.load(mid, get=self.get) if mid else None
                except Exception:  # noqa: BLE001
                    v = None
                if v is not None:
                    self._see(v)
            p = f.p_pct / 100.0 if f.p_pct > 1.0 else f.p_pct
            if self._note_forecast(mid, p, confidence=f.confidence, reason=f.reason):
                done += 1
            else:
                skipped.append(mid or "(blank)")
        return f"FORECASTS recorded {done}; {len(self.forecast_log)} market(s) forecast this run" + (f"; skipped (unknown, ended, unpriced or p outside 1-99): {', '.join(skipped)}" if skipped else "")

    def flush_forecasts(self) -> int:
        rows = list(self.forecast_log.values())
        store.append_bot_forecasts(rows)
        return len(rows)

    # ── browsing ─────────────────────────────────────────────────────────────────────────────────
    def t_search_markets(self, c: Call) -> tuple[str, str]:
        rows = browse.search(c.query, now=self.now, get=self.get, ends_within_h=c.ends_within_h or None, min_liquidity=c.min_liquidity or None, limit=c.limit or None,
                           horizon_h=self.s.horizon_h, min_hours=self.s.min_hours_left)
        for v in rows:
            self._see(v)
        if not rows:
            return "no market matched (the window, liquidity floor and category blocklist all apply)", ""
        return "\n".join(f"{r['id']} | {r['question']} | ends {r['ends']} ({r['hours_left']} h) | YES {r['yes']} | spread {r['spread']} | liq ${r['liquidity']:,} | {r['source']}"
                         for r in (browse.row(v, self.now) for v in rows)), ""

    def t_market(self, c: Call) -> tuple[str, str]:
        v = browse.load(c.market, get=self.get, with_path=True)
        if v is None:
            return f"unknown market {c.market!r}", ""
        self._see(v)
        return browse.dump(v, self.now), ""

    def _labels(self) -> dict[str, str]:
        held = book.holdings(self.ds)
        return {f"P{i}": mid for i, (mid, _) in enumerate(sorted(held.items(), key=lambda kv: -kv[1].cost), 1)}

    def t_portfolio(self, _c: Call | None = None) -> tuple[str, str]:
        held, ms = book.holdings(self.ds), store.markets()
        by_market = store.snapshots_by_market()
        fresh: dict[str, str] = {}
        for mid in held:                                   # a live mark for each position; a failure falls back to the last snapshot on file
            try:
                v = browse.load(mid, get=self.get)
            except Exception:  # noqa: BLE001
                v = None
            if v is not None and v.yes is not None:
                fresh[mid] = ""
                if store.due_for_snapshot(by_market, mid, self.now):
                    store.append_snapshots([self._snap(v)])
            else:
                fresh[mid] = " (price from the last snapshot)"
        prices = store.snapshots_by_market()
        pt = book.point(self.s.series, self.now, cash_=book.cash(self.ds), held=held, realised_=book.realised(self.ds), prices=prices)
        lines = [f"cash {_money(pt.cash)} | equity {_money(pt.equity)} (P&L {_money(pt.equity - self.s.bankroll)}) | invested {_money(sum(h.cost for h in held.values()))} "
                 f"({sum(h.cost for h in held.values()) / self.s.bankroll:.1%} of the bankroll at risk) of the {_money(self.s.exposure_frac * self.s.bankroll)} limit | "
                 f"activity floor {self.s.floor_pct:.0%} of the bankroll{f' - YOU ARE {_money(self.floor_gap())} UNDER IT' if self.floor_gap() else ' (met)'} | "
                 f"per-market limit {_money(self.s.position_frac * self.s.bankroll)} | realised so far {_money(book.realised(self.ds))}, unrealised {_money(pt.unrealised)}"]
        for lab, mid in self._labels().items():
            h, m = held[mid], ms.get(mid)
            p = book.last_price(prices.get(mid, []))
            value = h.shares * book.side_price(p, h.side) if p is not None else h.cost
            end = store.parse_iso(m.end_date) if m else None
            left = f"{(end - self.now).total_seconds() / 3600:.1f} h to resolution" if end else "no end time"
            lines.append(f"{lab} [{mid}] {h.side.upper()} {m.question if m else mid} | {h.shares:.1f} sh, entry {h.entry:.3f}, now "
                         f"{'?' if p is None else round(book.side_price(p, h.side), 3)}, cost {_money(h.cost)}, value {_money(value)}, unrealised {_money(value - h.cost)} ({(value - h.cost) / h.cost:+.0%}), "
                         f"realised on earlier sells {_money(sum(d.realised for d in self.ds if d.market_id == mid))}, {h.cost / self.s.bankroll:.1%} of bankroll | {left}{fresh[mid]}")
        if not held:
            lines.append("no open positions")
        lines += self.resting_lines(prices)
        return "\n".join(lines), ""

    def _resting_labels(self) -> dict[str, str]:
        return {f"R{i}": o.id for i, o in enumerate(resting.open_orders(self.sid), 1)}

    def resting_lines(self, prices: dict[str, list[Snapshot]]) -> list[str]:
        """The book's open resting orders, for the portfolio: label, id, what it waits for, the price now, and when it expires."""
        ms, out = store.markets(), []
        held_now = book.holdings(self.ds)
        for i, o in enumerate(resting.open_orders(self.sid), 1):
            m, p, held = ms.get(o.market_id), book.last_price(prices.get(o.market_id, [])), held_now.get(o.market_id)
            side = o.action.removeprefix("buy_") if o.action != "sell" else (held.side if held else "")
            price = "?" if p is None or not side else f"{book.side_price(p, side):.3f}"
            size = f"${o.usd:,.0f}" if o.action != "sell" else f"{o.fraction:.0%} of the position"
            end = store.parse_iso(o.expires_at)
            left = f"{(end - self.now).total_seconds() / 3600:.1f} h" if end else "?"
            out.append(f"R{i} [{o.id}] {o.action.replace('_', ' ').upper()} {m.question if m else o.market_id} [{o.market_id}] | limit {o.limit_price:.3f} all-in, price now {price} "
                       f"(before slippage) | {size} | expires in {left} | your p(YES) {o.p_yes:.2f}")
        return ["RESTING ORDERS (they fill by themselves between your runs when the price reaches the limit; cancel_resting to withdraw):", *out] if out else []

    def t_performance(self, _c: Call) -> tuple[str, str]:
        st = day_report.stats(self.ds, self.s.series)
        eq = " ".join(f"{d[5:]} {e:,.0f}" for d, e in st["equity"]) or "no history yet"
        trade = lambda t: f"{t['question'][:60]} {_money(t['pnl'])} in {t['hold_h']} h"  # noqa: E731
        grp = lambda g: f"{g['label']}: {g['n']} closed, {g['wins']} won, {_money(g['pnl'])}"  # noqa: E731
        lines = [f"equity by day: {eq}", f"closed trades {st['closed']}, won {st['wins']}, realised {_money(st['realised'])}, average hold {st['avg_hold_h']} h",
                 "best: " + ("; ".join(trade(t) for t in st["best"]) or "none"), "worst: " + ("; ".join(trade(t) for t in st["worst"]) or "none"),
                 "by horizon: " + (" | ".join(grp(g) for g in st["horizon"] if g["n"]) or "none yet"), "by category: " + (" | ".join(grp(g) for g in st["category"]) or "none yet")]
        return NL.join(lines), ""

    def t_size(self, c: Call) -> tuple[str, str]:
        v = browse.load(c.market, get=self.get)
        if v is None or v.yes is None:
            return f"no live price for {c.market!r}", ""
        if not 0.0 < c.p_yes < 1.0:
            return "give p_yes: your probability that the market resolves YES (between 0 and 1)", ""
        self._see(v)
        held, cash = book.holdings(self.ds).get(v.market.id), book.cash(self.ds)
        exposure = sum(h.cost for h in book.holdings(self.ds).values())
        room = min(cash, self.s.position_frac * self.s.bankroll - (held.cost if held else 0.0), self.s.exposure_frac * self.s.bankroll - exposure)
        w = sizing.trust(self.s.id)
        lines = [f"YES at {v.yes} (spread {v.spread}); your p(YES) {c.p_yes:.2f}; room under the caps and cash {_money(max(0.0, room))}; your trust {w:.2f} "
                 f"(stakes size on p shrunk toward the price: q = trust*p + (1-trust)*price; trust is earned by beating the market on contested markets)"]
        for side, q in (("yes", c.p_yes), ("no", 1 - c.p_yes)):
            cost = min(0.99, book.side_price(v.yes, side) + flags.SLIPPAGE)
            k = sizing.ceiling(c.p_yes, side, cost, self.s.bankroll, w)
            if k.full <= 0:
                lines.append(f"{side.upper()}: all-in price {cost:.3f}, your {q:.2f} shrunk to {k.q:.3f}: no edge, a buy would be held")
                continue
            lines.append(f"{side.upper()}: all-in price {cost:.3f}; your {q:.2f} shrunk to q={k.q:.3f}, edge {k.q - cost:+.3f} per share; full Kelly on q {k.full:.1%} of bankroll, "
                         f"{flags.KELLY_FRACTION:g}x = {_money(flags.KELLY_FRACTION * k.full * self.s.bankroll)}; ceiling {_money(k.stake)} ({k.why}); after the caps {_money(max(0.0, min(k.stake, room)))}")
        if held:
            lines.append(f"you hold {held.side.upper()} (cost {_money(held.cost)}): compare the expected value of holding with selling at the bid before adding")
        return NL.join(lines), ""

    def t_watchlist(self, c: Call) -> tuple[str, str]:
        mid = c.market.strip()
        if c.action in ("add", "remove") and mid:
            v = browse.load(mid, get=self.get) if c.action == "add" else None
            q = v.market.question if v else store.markets().get(mid).question if mid in store.markets() else ""
            store.append_watch(WatchEvent(id=f"wl-{len(store.watch_events()) + 1}-{mid}", at=self.now.isoformat(timespec="seconds"), market_id=mid, action=c.action,
                                          question=q, note=" ".join(c.reason.split())[:200], strategy=self.s.id))
        return self.watch_text(), ""

    def watch_text(self) -> str:
        w = store.watchlist(self.s.id)
        return NL.join(f"[{e.market_id}] {e.question} | since {e.at[:10]} | {e.note}" for e in w.values()) or "watchlist is empty"

    # ── the corpus ───────────────────────────────────────────────────────────────────────────────
    def _corpus(self, c: Call) -> tuple[str, str]:
        if self.corpus is None:
            return "the corpus index is not available on this machine; nothing to read", ""
        if not c.query.strip():
            return "give a query: an entity name or a few distinctive words", ""
        hits = research.run_query(self.corpus, research.Query(tool=c.tool, arg=c.query, since=c.since, kinds=c.kinds), today=self.now.date())  # type: ignore[arg-type]
        self.queries.append(f"{c.tool}({c.query.strip()[:80]})")
        lane = self._feed_lane(c, hits)
        self.shown.update(h.id for h in [*hits, *lane])
        out = [h.line(300) for h in hits]
        if lane:
            out += [f"— from the {research.lane_label(c.query, self.now.date())} —", *(h.line(300) for h in lane)]
        return "\n".join(out) or "nothing in the corpus", ""

    def _feed_lane(self, c: Call, hits: list[research.Hit]) -> list[research.Hit]:
        """The structured feed's rows for a search/about ask, minus what the normal hits show. The lab's frozen run_query is untouched; it can adopt this later as a new evidence-policy version."""
        if c.tool not in ("search", "about") or not flags.SEARCH_FEED_LANE:
            return []
        try:
            seen = {h.id for h in hits}
            return [h for h in research.feed_lane(self.corpus, c.query, since=c.since, kinds={k for k in c.kinds if k} or None, today=self.now.date()) if h.id not in seen]  # type: ignore[arg-type]
        except Exception:  # noqa: BLE001 - the lane is a bonus; the normal answer stands
            return []

    t_entity = t_about = t_search = t_timeline = t_related = t_series = _corpus

    def t_request_research(self, c: Call) -> tuple[str, str]:
        g = gaps.record(c.query, c.reason, market_id=c.market.strip() or self.s.id, question=self.considered.get(c.market.strip(), {}).get("question", ""), book=self.s.id,
                        kind="trade", at=self.now.isoformat(timespec="seconds"))
        self.queries.append(f"request_research({c.query.strip()[:80]})")
        return ("filed for the desk's research job; it lands in the corpus later, not in this run" if g else "not filed (empty, or already asked for this market)"), ""

    # ── orders ───────────────────────────────────────────────────────────────────────────────────
    def _snap(self, v: browse.View) -> Snapshot:
        return Snapshot(market_id=v.market.id, at=self.now.isoformat(timespec="seconds"), p=v.yes or 0.0, bid=v.bid, ask=v.ask,
                        last=num(v.raw.get("lastTradePrice")), volume=v.market.volume)

    def _line(self, action: str, v: browse.View | None, mid: str, c: Call, fill: guards.Fill, clips: list[str], requested: float) -> Decision:
        self.attempts += 1
        at = (self.now + timedelta(seconds=len(self.orders))).isoformat(timespec="seconds")
        end = store.parse_iso(v.market.end_date) if v else None
        cited = [i for i in c.cited if i in self.shown]
        return Decision(id=decision_id(mid, fill.action, f"{at}{self.s.id}{self.attempts}"), market_id=mid, at=at, day=at[:10], action=fill.action,  # type: ignore[arg-type]
                        requested=round(requested, 2), side=fill.side, price=fill.price, shares=fill.shares, cash_flow=fill.cash_flow,  # type: ignore[arg-type]
                        realised=fill.realised, rationale=" ".join(c.reason.split())[:420], clips=clips, ours=c.p_yes if 0.0 < c.p_yes < 1.0 else None, market=v.yes if v else None,
                        model="house-" + self.s.effort, prompt_version=self.s.prompt_version, usd=0.0, book=self.s.id, evidence_ids=cited, basis=" ".join(c.basis.split())[:1800],
                        hours_to_end=round((end - self.now).total_seconds() / 3600, 1) if end else None)

    def _order(self, kind: str, c: Call) -> tuple[str, str]:
        mid = c.market.strip()
        label = self._labels().get(mid.upper())
        mid = label or mid
        requested = max(0.0, float(c.usd or 0.0))
        if kind == "sell" and c.all:
            requested = 1e12
        v = browse.load(mid, get=self.get) if mid else None
        held = book.holdings(self.ds).get(mid)
        why = ""
        if self.attempts >= self.s.max_orders:
            why = f"order limit for this run reached ({self.s.max_orders})"
        elif v is None:
            why = f"unknown market {mid!r}"
        elif kind == "buy":
            why = browse.tradable_why(v, self.now, horizon_h=self.s.horizon_h, min_hours=self.s.min_hours_left)
            if c.side not in ("yes", "no"):
                why = why or "side must be yes or no"
            if not 0.0 < c.p_yes < 1.0:
                why = why or "give p_yes: your probability of YES (a fraction between 0 and 1); the stake is sized on it, shrunk by your trust"
        elif v.raw.get("closed") or v.raw.get("active") is False:
            why = "the market is closed to trading (awaiting its resolution)"
        elif v.yes is None:
            why = "no live price"
        action = "sell" if kind == "sell" else f"buy_{c.side}"
        floor_clip, floor_sized = "", False
        under = kind == "buy" and not why and v is not None and v.yes is not None and self.exposure() < self.s.floor_pct * self.s.bankroll
        if under:
            assert v is not None and v.yes is not None
            q = c.p_yes if c.side == "yes" else 1.0 - c.p_yes
            edge = q - book.side_price(v.yes, c.side) if 0.0 < c.p_yes < 1.0 else 0.0
            if c.floor or edge < flags.EDGE_MIN:                       # a position taken to fill the floor, not for a stated edge: small, and tagged
                size = guards.floor_stake(c.p_yes, c.side, v.yes, self.s.bankroll, sizing.trust(self.s.id))
                floor_clip = f"floor position (no real edge): sized by your own probability, {_money(size)}" if requested > size or requested <= 0 else ""
                requested = min(requested, size) if requested > 0 else size
                floor_sized = True                                       # already sized mechanically (the ticket at worst): the edge test would only void it
            else:
                under = False
        if why:
            fill = guards.Fill("hold", held.side if held else "", clips=[f"refused: {why}"])
        else:
            assert v is not None and v.yes is not None
            fill = guards.apply(action, requested, held=held, yes_price=v.yes, cash=book.cash(self.ds), exposure=sum(h.cost for h in book.holdings(self.ds).values()),
                                tradable=True, position_frac=self.s.position_frac, exposure_frac=self.s.exposure_frac, bankroll=self.s.bankroll,
                                p_yes=c.p_yes if kind == "buy" and not floor_sized and 0.0 < c.p_yes < 1.0 else None, trust=sizing.trust(self.s.id))
        d = self._line(action, v, mid, c, fill, [*([floor_clip] if floor_clip else []), *fill.clips], min(requested, 1e9))
        if under and d.action in ("buy_yes", "buy_no"):
            d.tag = "floor"
        if v is not None and 0.0 < c.p_yes < 1.0 and mid not in self.forecast_log:
            self._see(v)
            self._note_forecast(mid, c.p_yes, reason=c.reason)         # an order carries the agent's own probability: it is a forecast too
        store.append_decisions([d])
        self.ds.append(d)
        self.orders.append(d.id)
        if v is not None:
            self._see(v)
        if d.action in ("buy_yes", "buy_no") and v is not None:
            if mid not in store.markets():
                store.save_markets([v.market.model_copy(update={"origin": "day"})])   # "day" = brought in by an agentic bot alone: never desk-forecast
            store.append_snapshots([self._snap(v)])
        return self._answer(d), d.id

    def _answer(self, d: Decision) -> str:
        left = f"cash now {_money(book.cash(self.ds))}"
        trimmed = f" Trimmed or refused: {'; '.join(d.clips)}." if d.clips else ""
        if d.action in ("buy_yes", "buy_no"):
            return f"FILLED buy {d.side.upper()} {_money(-d.cash_flow)} = {d.shares:.1f} shares at {d.price:.3f} (quote plus slippage); {left}.{trimmed}"
        if d.action == "sell":
            return f"FILLED sell {d.side.upper()} {d.shares:.1f} shares at {d.price:.3f} for {_money(d.cash_flow)}, realised {_money(d.realised)}; {left}.{trimmed}"
        return f"NOT FILLED.{trimmed or ' nothing to do.'} {left}."

    def t_place_resting(self, c: Call) -> tuple[str, str]:
        mid = c.market.strip()
        mid = self._labels().get(mid.upper()) or mid
        v = browse.load(mid, get=self.get) if mid else None
        if v is None or v.yes is None:
            return f"NOT PLACED: no live price for {mid!r}", ""
        why = (browse.tradable_why(v, self.now, horizon_h=self.s.horizon_h, min_hours=self.s.min_hours_left) if c.way == "buy"
               else "the market is closed to trading" if v.raw.get("closed") or v.raw.get("active") is False else "")
        if why:
            return f"NOT PLACED: {why}", ""
        o, msg = resting.place(self.s, self.ds, now=self.now, market_id=mid, end=store.parse_iso(v.market.end_date), yes=v.yes, way=c.way, side=c.side, limit=c.limit_price, usd=c.usd,
                               fraction=1.0 if c.all else c.fraction, p_yes=c.p_yes, hours=c.hours, reason=c.reason)
        if o is None:
            return f"NOT PLACED: {msg}", ""
        self._see(v)
        if mid not in self.forecast_log:
            self._note_forecast(mid, c.p_yes, reason=c.reason)         # an order carries the agent's own probability: it is a forecast too
        if mid not in store.markets():
            store.save_markets([v.market.model_copy(update={"origin": "day"})])   # tracked by the mirror from now on, so the fill pass has prices
        store.append_snapshots([self._snap(v)])
        return msg, o.id

    def t_cancel_resting(self, c: Call) -> tuple[str, str]:
        ref = c.order.strip() or c.market.strip()
        ref = self._resting_labels().get(ref.upper(), ref)
        return resting.cancel(self.sid, ref, self.now, c.reason), ref

    def t_buy(self, c: Call) -> tuple[str, str]:
        return self._order("buy", c)

    def t_sell(self, c: Call) -> tuple[str, str]:
        return self._order("sell", c)

