"""
The market mirror: free, read-only, no model.

One pass (the ``markets`` timer, every few hours):
1. DISCOVER. Sweep the Gamma events of each tag in ``flags.TAGS``; keep open binary markets that are liquid enough, end inside the window and
   MAP to a theater or country we cover (``mapping.py``). Highest volume first, at most ``flags.MAX_OPEN``.
2. SNAPSHOT. Write the YES price of every tracked market (at most one per ``flags.SNAPSHOT_MIN_GAP_H``); a market seen for the first time also
   gets its CLOB daily history backfilled so it has a past.
3. RESOLVE. A tracked market the sweep no longer lists is fetched by id; one that has finally resolved is closed in the store with its outcome
   (yes / no / void). That is the ground truth everything is scored against.

Each tag and each market is isolated: a failed request is recorded and never stops the pass.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Any

from . import flags, mapping, polymarket, store
from .contracts import Market
from .polymarket import Fetch


def _wanted(m: Market, now: datetime) -> bool:
    end = store.parse_iso(m.end_date)
    if m.liquidity < flags.MIN_LIQUIDITY_USD or m.volume < flags.MIN_VOLUME_USD:
        return False
    return end is None or timedelta(hours=flags.MIN_HOURS_LEFT) <= end - now <= timedelta(days=flags.MAX_DAYS_AHEAD)


def discover(get: Fetch, vocab: list[mapping.TheaterVocab], now: datetime, errors: dict[str, str]) -> dict[str, tuple[Market, dict[str, Any]]]:
    found: dict[str, tuple[Market, dict[str, Any]]] = {}
    for tag in flags.TAGS:
        try:
            events = polymarket.events_for_tag(tag, get)
        except Exception as exc:  # noqa: BLE001 - one tag down must not stop the others
            errors[f"tag:{tag}"] = f"{type(exc).__name__}: {str(exc)[:160]}"
            continue
        for ev in events:
            etags = {t.get("slug") for t in ev.get("tags") or [] if isinstance(t, dict)}
            if etags & set(flags.BLOCK_TAGS):
                continue
            for raw in ev.get("markets") or []:
                if not isinstance(raw, dict) or raw.get("closed") or raw.get("active") is False or str(raw.get("id")) in found:
                    continue
                m = polymarket.parse_market(raw, ev)
                if m is None or not _wanted(m, now):
                    continue
                theaters, countries, score = mapping.map_market(m.question, m.event_title, vocab)
                if score < flags.MIN_MAP_SCORE:
                    continue
                found[m.id] = (m.model_copy(update={"theaters": theaters, "countries": countries, "map_score": score}), raw)
    top = sorted(found.values(), key=lambda mr: -mr[0].volume)[:flags.MAX_OPEN]
    return {m.id: (m, raw) for m, raw in top}


def refresh(get: Fetch | None = None, *, now: datetime | None = None, vocab: list[mapping.TheaterVocab] | None = None) -> dict[str, Any]:
    from algent_backend import polite_http

    get = get or polymarket.fetch
    now = now or datetime.now(UTC)
    at = now.isoformat(timespec="seconds")
    polite_http.clear_memo()
    errors: dict[str, str] = {}
    vocab = vocab if vocab is not None else mapping.latest_vocab()
    found = discover(get, vocab, now, errors)
    known = store.markets()
    out = {"as_of": at, "discovered": len(found), "new": 0, "snapshots": 0, "history": 0, "resolved": 0, "tracked_open": 0}
    if not found and len(errors) >= len(flags.TAGS):                    # nothing came back at all: a failure, not "no markets"
        store.save_status(last_error=next(iter(errors.values())), last_error_at=at, errors=errors)
        return {**out, "error": "every tag sweep failed", "errors": errors}
    rows: list[Market] = []
    raws: dict[str, dict[str, Any]] = {}
    for mid, (m, raw) in found.items():
        rows.append(m)
        raws[mid] = raw
    # tracked, still-open markets the sweep did not list: look each up (this is where a resolution is seen)
    for mid, old in known.items():
        if old.status != "open" or mid in raws:
            continue
        try:
            raw = polymarket.market_by_id(mid, get)
        except Exception as exc:  # noqa: BLE001
            errors[f"market:{mid}"] = f"{type(exc).__name__}: {str(exc)[:120]}"
            continue
        if raw is None:
            continue
        raws[mid] = raw
        rows.append(old)
    resolved = []
    for m in rows:
        outcome, when = polymarket.resolution(raws[m.id])
        if outcome:
            m = m.model_copy(update={"status": "void" if outcome == "void" else "resolved", "outcome": outcome, "resolved_at": when})
            out["resolved"] += 1
        elif raws[m.id].get("closed"):
            continue                                                   # closed, not yet finally resolved: leave as it was
        raw = raws[m.id]
        resolved.append(m.model_copy(update={"volume": polymarket.num(raw.get("volumeNum")) or m.volume,
                                             "liquidity": polymarket.num(raw.get("liquidityNum")) or m.liquidity}))
    res = store.save_markets(resolved)
    out["new"] = res["new"]
    by_market = store.snapshots_by_market()
    snaps = []
    for m in resolved:
        if m.status != "open":
            continue
        out["tracked_open"] += 1
        if m.id not in known and m.token_yes:
            try:
                hist = polymarket.history(m.token_yes, m.id, get)
                snaps += hist
                out["history"] += len(hist)
            except Exception as exc:  # noqa: BLE001
                errors[f"history:{m.id}"] = f"{type(exc).__name__}: {str(exc)[:120]}"
        if store.due_for_snapshot(by_market, m.id, now) and (s := polymarket.snapshot_of(raws[m.id], m.id, at)) is not None:
            snaps.append(s)
            out["snapshots"] += 1
    store.append_snapshots(snaps)
    store.save_status(last_ok=at, last_error="" if not errors else next(iter(errors.values())), errors=errors, summary=out)
    return {**out, "errors": errors}
