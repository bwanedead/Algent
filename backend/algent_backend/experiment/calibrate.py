"""
Calibration boards: re-score stored forecasts through each calibration policy (``calibration.py``) with no model call, and put raw and calibrated side by side.

``lab_board`` (``newsroom lab calibrate``): for every stored protocol that has runs, every policy; each forecast is mapped by a fit made ONLY on that protocol's
(and, for ``platt-live``, the live bots') forecasts resolved strictly before the forecast's cutoff, in time order, so the board is the out-of-sample answer to "would
recalibrating have helped".
``live_board`` (``newsroom lab live-board``): the same scorer on the live strategies' resolved ``BotForecast``s (the real out-of-sample data: hundreds of
forecasts, each carrying the market price at the moment it was made). One forecast per (strategy, market), the last before the market resolved, like
``markets.bot_forecasts.skill_stats``; a map for a forecast is fitted on earlier-RESOLVED forecasts of the same group.
``track_block`` is the small summary the track record publishes (``lab_block.json`` beside the store; the markets side reads that file, never this package).
"""

from __future__ import annotations

import json
from typing import Any

from . import calibration, flags, genealogy, score, store
from .calibration import Fitter, Obs

Row = dict[str, Any]
BLOCK = "lab_block.json"


# ── observations ──────────────────────────────────────────────────────────────────────────────────
def lab_rows(*, resolve_now: bool = True) -> list[Row]:
    """Every stored controlled forecast whose question has resolved yes/no: protocol, question, p (None = abstained), outcome, cutoff, resolution time, market price."""
    qs = score.questions()
    res = {qid: (score.resolve(q) if resolve_now else score._stored(qid)) for qid, q in qs.items()}
    out = []
    for r in score.runs():
        rs, q = res.get(r.question_id), qs.get(r.question_id)
        if r.mode != "controlled" or q is None or rs is None or rs.outcome not in ("yes", "no"):
            continue
        out.append({"protocol": r.protocol_id, "question": q.id, "p": r.p, "o": 1 if rs.outcome == "yes" else 0, "cutoff": q.cutoff, "resolved_at": rs.resolved_at,
                    "market_p": q.reference.get("market_p"), "usd": r.usd})
    return out


def live_rows(strategies: tuple[str, ...] = (), *, forecasts: list[Any] | None = None, markets: dict[str, Any] | None = None) -> list[Row]:
    """The live bots' resolved forecasts, one per (strategy, market): the last made before the market resolved. ``at`` is when the bot said it."""
    from algent_backend.markets import store as ms
    from algent_backend.markets.bot_forecasts import scorable

    ms_ = ms.markets() if markets is None else markets
    last: dict[tuple[str, str], Any] = {}
    for f in sorted(ms.bot_forecasts() if forecasts is None else forecasts, key=lambda f: f.at):
        m = ms_.get(f.market_id)
        if strategies and f.strategy not in strategies:
            continue
        if scorable(f, m):
            last[(f.strategy, f.market_id)] = f
    return [{"strategy": f.strategy, "market": f.market_id, "p": f.p, "o": 1 if ms_[f.market_id].outcome == "yes" else 0, "cutoff": f.at, "resolved_at": ms_[f.market_id].resolved_at,
             "market_p": f.market} for f in last.values()]


def observations(rows: list[Row]) -> list[Obs]:
    return [Obs(p=r["p"], o=r["o"], resolved_at=r["resolved_at"], key=str(r.get("question") or r.get("market") or "")) for r in rows if r["p"] is not None and r["resolved_at"]]


# ── evaluation ────────────────────────────────────────────────────────────────────────────────────
def bins(pairs: list[tuple[float, int]]) -> list[dict[str, Any]]:
    """Reliability bins (same shape the track record already draws): said vs happened."""
    n = flags.CALIBRATION_BINS
    by: dict[int, list[tuple[float, int]]] = {}
    for p, o in pairs:
        by.setdefault(min(n - 1, int(p * n)), []).append((p, o))
    return [{"low": b / n, "high": (b + 1) / n, "n": len(v), "mean_p": round(sum(p for p, _ in v) / len(v), 4), "hit_rate": round(sum(o for _, o in v) / len(v), 4)} for b, v in sorted(by.items())]


def _side(pairs: list[tuple[float, int, float | None]]) -> dict[str, Any]:
    br = [score.brier(p, o) for p, o, _ in pairs]
    vs = [score.brier(p, o) - score.brier(m, o) for p, o, m in pairs if m is not None]
    return {"brier": score.mean_se(br)[0], "brier_minus_market": score.mean_se(vs)[0], "se": score.mean_se(vs)[1], "n_vs_market": len(vs), "bins": bins([(p, o) for p, o, _ in pairs])}


def evaluate(rows: list[Row], fitter: Fitter, pv: Any) -> dict[str, Any]:
    """Raw and calibrated side by side over the rows that have a probability. Each map is fitted only on what resolved before the row's cutoff."""
    raw, cal, n_fitted, reasons = [], [], 0, {}
    for r in rows:
        if r["p"] is None:
            continue
        pc, m = fitter.apply(pv, r["p"], r["cutoff"])
        n_fitted += m.fitted
        reasons[m.kind] = reasons.get(m.kind, 0) + 1
        raw.append((r["p"], r["o"], r["market_p"]))
        cal.append((pc, r["o"], r["market_p"]))
    a, b = _side(raw), _side(cal)
    gain = None if a["brier_minus_market"] is None or b["brier_minus_market"] is None else round(b["brier_minus_market"] - a["brier_minus_market"], 4)
    return {"policy": pv.ref, "n": len(raw), "n_fitted": n_fitted, "raw": a, "calibrated": b, "change_in_brier_minus_market": gain, "why_not_fitted": {k: v for k, v in reasons.items() if k not in ("fitted", "identity")}}


def lab_board(*, only: set[str] | None = None, live_strategies: tuple[str, ...] = (), rows: list[Row] | None = None, live: list[Row] | None = None,
              resolve_now: bool = True) -> dict[str, Any]:
    """Every stored protocol with runs x every calibration policy. The fit pool is the protocol's runs on ALL questions; ``only`` restricts what is scored."""
    allrows = lab_rows(resolve_now=resolve_now) if rows is None else rows
    liverows = live_rows(live_strategies) if live is None else live
    names = {pid: p.name for pid, p in genealogy.all_protocols().items()}
    out: dict[str, Any] = {}
    for pid in sorted({r["protocol"] for r in allrows}):
        mine = [r for r in allrows if r["protocol"] == pid]
        fitter = Fitter(lab=observations(mine), live=observations(liverows))
        scored = [r for r in mine if only is None or r["question"] in only]
        out[pid] = {"name": names.get(pid, pid), "policies": {pv.name: evaluate(scored, fitter, pv) for pv in calibration.all_policies(live_strategies)}}
    return {"protocols": out, "live_sample": len(observations(liverows)),
            "note": "each forecast is mapped by a fit on forecasts that resolved strictly before its cutoff; negative change = recalibration helped; platt-live also uses the live bots' forecasts"}


def live_board(*, strategies: tuple[str, ...] = (), rows: list[Row] | None = None) -> dict[str, Any]:
    """The live strategies scored by the lab's scorer, raw vs recalibrated by a map fitted on earlier-resolved forecasts of the same group (a strategy, or all)."""
    allrows = live_rows(strategies) if rows is None else rows
    pv = calibration.platt_live()
    groups: dict[str, list[Row]] = {s: [r for r in allrows if r["strategy"] == s] for s in sorted({r["strategy"] for r in allrows})}
    groups["all"] = allrows
    out = {}
    for name, g in groups.items():
        out[name] = evaluate(g, Fitter(live=observations(g)), pv)
        out[name]["policy"] = pv.ref
    head = out.get("all")
    return {"groups": out, "headline": headline(head) if head else None, "note": "one forecast per (strategy, market), the last before resolution; vs the market price at the moment it was said"}


def headline(ev: dict[str, Any]) -> dict[str, Any] | None:
    r, c = ev["raw"]["brier_minus_market"], ev["calibrated"]["brier_minus_market"]
    if r is None or c is None:
        return None
    return {"n": ev["raw"]["n_vs_market"], "n_fitted": ev["n_fitted"], "raw": r, "calibrated": c,
            "text": f"if we had recalibrated, Brier vs market would be {c:+.3f} instead of {r:+.3f} on {ev['raw']['n_vs_market']} resolved (lower is better; negative beats the market)"}


# ── published summary ─────────────────────────────────────────────────────────────────────────────
def track_block(*, board: dict[str, Any] | None = None, live: dict[str, Any] | None = None) -> dict[str, Any]:
    """The 'recipe lab' block of the track record: the best stored protocol vs the market (raw and calibrated, with n), and the live-board calibration headline with
    reliability bins. Plain numbers only; nothing here changes how any bot trades."""
    board = lab_board() if board is None else board
    live = live_board() if live is None else live
    best = None
    for p in board["protocols"].values():
        ev = p["policies"].get("platt")
        if ev is None or ev["raw"]["brier_minus_market"] is None:
            continue
        if best is None or ev["raw"]["brier_minus_market"] < best["raw"]["brier_minus_market"]:
            best = {"protocol": p["name"], "n": ev["raw"]["n_vs_market"], "raw": ev["raw"]["brier_minus_market"], "calibrated": ev["calibrated"]["brier_minus_market"], "n_fitted": ev["n_fitted"],
                    "bins_raw": ev["raw"]["bins"], "bins_calibrated": ev["calibrated"]["bins"]}
    lg = (live.get("groups") or {}).get("all")
    live_block = None
    if lg and live.get("headline"):
        live_block = {**live["headline"], "bins_raw": lg["raw"]["bins"], "bins_calibrated": lg["calibrated"]["bins"]}
    return {"as_of": store.now_iso(), "best": best, "live": live_block,
            "basis": "Brier minus the market's own Brier at the same moment: below zero beats the market. Calibration maps are fitted only on forecasts that had already resolved."}


def write_block(block: dict[str, Any]) -> str:
    """Replace ``lab_block.json`` beside the store (a derived view, not an experiment record, so it is rewritten rather than written once)."""
    p = store.path(BLOCK)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(block, indent=1, sort_keys=True), encoding="utf-8")
    return str(p)


# ── text ──────────────────────────────────────────────────────────────────────────────────────────
def render_lab(board: dict[str, Any]) -> str:
    head = f"{'protocol':26} {'policy':16} {'n':>3} {'fit':>3} {'raw b-m':>8} {'cal b-m':>8} {'change':>7}"
    lines = [head, "-" * len(head)]
    f = lambda v: "-" if v is None else f"{v:+.3f}"  # noqa: E731
    for p in board["protocols"].values():
        for ev in p["policies"].values():
            lines.append(f"{p['name'][:26]:26} {ev['policy'].split('/')[-1][:16]:16} {ev['n']:>3} {ev['n_fitted']:>3} {f(ev['raw']['brier_minus_market']):>8} "
                         f"{f(ev['calibrated']['brier_minus_market']):>8} {f(ev['change_in_brier_minus_market']):>7}")
    lines.append(f"b-m = Brier minus market (negative beats the market); fit = forecasts actually recalibrated; live sample available: {board['live_sample']}")
    return "\n".join(lines)


def render_live(board: dict[str, Any]) -> str:
    head = f"{'group':22} {'n':>4} {'fit':>4} {'raw b-m':>8} {'cal b-m':>8} {'change':>7}"
    lines = [head, "-" * len(head)]
    f = lambda v: "-" if v is None else f"{v:+.3f}"  # noqa: E731
    for name, ev in board["groups"].items():
        lines.append(f"{name[:22]:22} {ev['n']:>4} {ev['n_fitted']:>4} {f(ev['raw']['brier_minus_market']):>8} {f(ev['calibrated']['brier_minus_market']):>8} {f(ev['change_in_brier_minus_market']):>7}")
    if board["headline"]:
        lines.append(board["headline"]["text"])
    return "\n".join(lines)
