"""
Resolution and scoring. ONE resolution rule per question, stored write-once the first time the outcome is known, so every protocol is judged by the same
fact and a later edit of the source cannot change a score. Scores are computed from the stored forecasts and resolutions only (never by re-running a
protocol) and are kept apart from trading P&L. Scoreboards are separate per experiment mode; cost is reported beside the score.

Brier and log score for the forecast; the same two for the market's price at the cutoff and for a base rate, when the question carries them. Abstentions are
counted and listed, not dropped. A difference between protocols comes with a standard error over the shared questions (None until there are two).
"""

from __future__ import annotations

import math
from typing import Any

from . import flags, store
from .contracts import Question, Resolution, RunRecord

RULE = "polymarket-outcome@1"


def brier(p: float, o: int) -> float:
    return (p - o) ** 2


def log_score(p: float, o: int) -> float:
    p = min(0.999, max(0.001, p))
    return -(o * math.log(p) + (1 - o) * math.log(1 - p))


def resolve(q: Question) -> Resolution | None:
    """The stored resolution, or one made now from the markets store if the market has settled (the only rule so far)."""
    raw = store.read_json(f"resolutions/{q.id}.json")
    if raw:
        return Resolution.model_validate(raw)
    if not q.source.startswith("market:"):
        return None
    from algent_backend.markets import store as ms

    m = ms.markets().get(q.source.split(":", 1)[1])
    if m is None or m.status == "open" or m.outcome not in ("yes", "no", "void"):
        return None
    r = Resolution(question_id=q.id, outcome=m.outcome, rule=RULE, resolved_at=m.resolved_at, recorded_at=store.now_iso())
    store.write_once(f"resolutions/{q.id}.json", r)
    return r


def questions() -> dict[str, Question]:
    out = {}
    for name in store.listing("questions"):
        raw = store.read_json(f"questions/{name}")
        if raw:
            q = Question.model_validate(raw)
            out[q.id] = q
    return out


def runs() -> list[RunRecord]:
    return [RunRecord.model_validate(r) for n in store.listing("runs") if (r := store.read_json(f"runs/{n}/run.json"))]


def row(r: RunRecord, q: Question, res: Resolution) -> dict[str, Any]:
    o = 1 if res.outcome == "yes" else 0
    chains = (store.read_json(f"runs/{r.run_id}/manifest.json") or {}).get("chains") or {}
    out: dict[str, Any] = {"n_shown": chains.get("n_shown"), "n_independent": chains.get("n_independent"), "run_id": r.run_id, "question": q.id, "protocol": r.protocol_id, "branch": r.branch_id, "mode": r.mode, "p": r.p, "outcome": res.outcome,
                           "usd": r.usd, "abstained": r.p is None}
    if r.p is not None:
        out.update(brier=brier(r.p, o), log=log_score(r.p, o))
    aw = store.read_json(f"runs/{r.run_id}/aware.json")
    if aw and aw.get("p") is not None:                                         # the market-aware second output, scored apart from the independent one
        out.update(p_aware=aw["p"], brier_aware=brier(aw["p"], o), usd=out["usd"] + aw.get("usd", 0.0))
    mp, br = q.reference.get("market_p"), q.reference.get("base_rate")
    if mp is not None:
        out.update(market_brier=brier(mp, o), market_log=log_score(mp, o))
    if br is not None:
        out.update(base_brier=brier(br, o), base_log=log_score(br, o))
    return out


def mean_se(xs: list[float]) -> tuple[float | None, float | None]:
    if not xs:
        return None, None
    m = sum(xs) / len(xs)
    if len(xs) < 2:
        return round(m, 4), None
    return round(m, 4), round(math.sqrt(sum((x - m) ** 2 for x in xs) / (len(xs) - 1) / len(xs)), 4)


def aware_summary(rows: list[dict[str, Any]]) -> dict[str, Any] | None:
    """Independent skill vs mispricing detection over the runs that also have a market-aware estimate. ``independent_minus_market``: does the blind estimate beat the
    price. ``aware_minus_market``: does the estimate made after seeing the price beat it. ``aware_minus_independent``: what seeing the price changed (negative = helped)."""
    ar = [r for r in rows if "brier_aware" in r and "market_brier" in r]
    if not ar:
        return None
    return {"n": len(ar), "independent_minus_market": mean_se([r["brier"] - r["market_brier"] for r in ar])[0], "aware_minus_market": mean_se([r["brier_aware"] - r["market_brier"] for r in ar])[0],
            "aware_minus_independent": mean_se([r["brier_aware"] - r["brier"] for r in ar])[0]}


def calibration(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    n = flags.CALIBRATION_BINS
    bins: dict[int, list[tuple[float, int]]] = {}
    for r in rows:
        if r["p"] is not None:
            bins.setdefault(min(n - 1, int(r["p"] * n)), []).append((r["p"], 1 if r["outcome"] == "yes" else 0))
    return [{"bin": f"{b / n:.1f}-{(b + 1) / n:.1f}", "n": len(v), "mean_p": round(sum(p for p, _ in v) / len(v), 3), "freq_yes": round(sum(o for _, o in v) / len(v), 3)}
            for b, v in sorted(bins.items())]


def scoreboard(*, resolve_now: bool = True, only: set[str] | None = None) -> dict[str, Any]:
    qs = {k: v for k, v in questions().items() if only is None or k in only}
    resolved = {qid: res for qid, q in qs.items() if (res := (resolve(q) if resolve_now else _stored(qid))) and res.outcome != "void"}
    rows = [row(r, qs[r.question_id], resolved[r.question_id]) for r in runs() if r.question_id in resolved]
    board: dict[str, Any] = {}
    for mode in sorted({r["mode"] for r in rows}):
        mrows = [r for r in rows if r["mode"] == mode]
        per: dict[str, Any] = {}
        for pid in sorted({r["protocol"] for r in mrows}):
            pr = [r for r in mrows if r["protocol"] == pid]
            sc = [r for r in pr if not r["abstained"]]
            vs_mkt = [r["brier"] - r["market_brier"] for r in sc if "market_brier" in r]
            vs_base = [r["brier"] - r["base_brier"] for r in sc if "base_brier" in r]
            per[pid] = {"n": len(pr), "abstained": len(pr) - len(sc), "brier": mean_se([r["brier"] for r in sc])[0], "brier_se": mean_se([r["brier"] for r in sc])[1], "log": mean_se([r["log"] for r in sc])[0],
                        "log_se": mean_se([r["log"] for r in sc])[1],
                        "brier_minus_market": mean_se(vs_mkt)[0], "brier_minus_base": mean_se(vs_base)[0], "usd": round(sum(r["usd"] for r in pr), 4),
                        "calibration": calibration(sc), "aware": aware_summary(sc)}
        pairs = {}
        pids = sorted(per)
        for i, a in enumerate(pids):
            for b in pids[i + 1:]:
                by_q_a = {r["question"]: r for r in mrows if r["protocol"] == a and not r["abstained"]}
                by_q_b = {r["question"]: r for r in mrows if r["protocol"] == b and not r["abstained"]}
                shared = by_q_a.keys() & by_q_b.keys()
                m, se = mean_se([by_q_a[k]["brier"] - by_q_b[k]["brier"] for k in shared])
                lm, lse = mean_se([by_q_a[k]["log"] - by_q_b[k]["log"] for k in shared])
                pairs[f"{a} - {b}"] = {"n_shared": len(shared), "brier_diff": m, "se": se, "log_diff": lm, "log_se": lse,
                                       "note": "negative = first is better; one question is an anecdote, not a result"}
        board[mode] = {"protocols": per, "differences": pairs, "rows": mrows}
    return {"modes": board, "unresolved": sorted(set(qs) - set(resolved))}


def _stored(qid: str) -> Resolution | None:
    raw = store.read_json(f"resolutions/{qid}.json")
    return Resolution.model_validate(raw) if raw else None
