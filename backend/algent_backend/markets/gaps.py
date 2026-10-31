"""
Gaps: what the bots needed and the corpus did not hold. A gap is a REQUEST, not a lookup: ``record`` appends it to ``gaps.jsonl``; the bot never
gets a web result. A daily capped job (``fill``, registry job ``markets-gaps``) clusters near-duplicate asks, takes the most-asked, and runs each as a
profile research run through the existing pipeline (``newsroom run --brief ... --to profile``), whose profile lands in the profile store and the
corpus index like any other and is stamped ``requested_by: markets``. The bot reads it next time as corpus content.

Spend is bounded three ways: ``flags.GAP_FILL_USD_PER_DAY`` (operator-authorised, $0.50), ``GAP_FILL_MAX_PER_DAY`` runs, and a topic filled in the last
``GAP_REFILL_DAYS`` days is not run again. A run is booked at ``GAP_FILL_EST_USD`` whether or not it succeeds (a failed run has usually spent), so the
cap is a ceiling, not a hope.
"""

from __future__ import annotations

import json
import re
import subprocess
import sys
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from typing import Any

from . import flags, store
from .contracts import Gap, GapFill, gap_id

_STOP = frozenset("the and for with from that this into over about what will have been are was were not but its their our any all new more than how why who when where "
                  "does did can may might would could should out off per via vs".split())
_SIM = 0.6                                                  # token-set overlap (Jaccard) at which two asks are the same request
Runner = Callable[[str, str], dict[str, Any]]


def tokens(text: str) -> frozenset[str]:
    return frozenset(t for t in re.findall(r"[a-z0-9]{3,}", text.casefold()) if t not in _STOP)


def cluster_key(topic: str) -> str:
    return " ".join(sorted(tokens(topic)))[:120]


def _same(a: frozenset[str], b: frozenset[str]) -> bool:
    return bool(a and b) and len(a & b) / len(a | b) >= _SIM


def record(topic: str, why: str, *, market_id: str, question: str = "", book: str = "daily", kind: str = "forecast", at: str | None = None) -> Gap | None:
    """Append one ask. Empty or token-less topics are dropped; asking twice for the same market and topic is one line."""
    topic = " ".join((topic or "").split())[:160]
    if not tokens(topic):
        return None
    at = at or store.now_iso()
    key = tokens(topic)
    if any(g.market_id == market_id and _same(tokens(g.topic), key) for g in store.gaps()):
        return None
    g = Gap(id=gap_id(market_id, topic, at), at=at, day=at[:10], topic=topic, why=" ".join((why or "").split())[:300], market_id=market_id,
            question=question[:200], book=book, kind=kind)
    store.append_gaps([g])
    return g


@dataclass
class Cluster:
    topic: str
    key: str
    asks: int = 0
    markets: list[str] = field(default_factory=list)
    questions: list[str] = field(default_factory=list)
    why: str = ""
    last_at: str = ""
    filled_at: str = ""
    toks: frozenset[str] = frozenset()
    refill: bool = False                                    # a second run for a cluster asked again after its fill (gap_loop); ``why`` then carries the sharper brief


def clusters(now: datetime | None = None, *, days: int = 30) -> list[Cluster]:
    """Asks of the last ``days`` days merged by similarity, most-asked first, each marked filled when a research run covered it inside the refill window."""
    now = now or datetime.now(UTC)
    floor = now - timedelta(days=days)
    out: list[Cluster] = []
    for g in sorted(store.gaps(), key=lambda g: g.at):
        t = store.parse_iso(g.at)
        if t is None or t < floor:
            continue
        gt = tokens(g.topic)
        c = next((c for c in out if _same(c.toks, gt)), None)
        if c is None:
            c = Cluster(topic=g.topic, key=cluster_key(g.topic), toks=gt)
            out.append(c)
        c.asks += 1
        c.markets = list(dict.fromkeys([*c.markets, g.market_id]))
        if g.question and g.question not in c.questions:
            c.questions.append(g.question)
        c.why, c.last_at, c.topic = g.why or c.why, g.at, g.topic
    refill = timedelta(days=flags.GAP_REFILL_DAYS)
    for f in store.gap_fills():
        ft = store.parse_iso(f.at)
        if ft is None or now - ft > refill or not f.ok:
            continue
        for c in out:
            if _same(c.toks, tokens(f.topic)):
                c.filled_at = max(c.filled_at, f.at)
    return sorted(out, key=lambda c: (c.asks, c.last_at), reverse=True)


def top(n: int = 10, now: datetime | None = None) -> list[dict[str, Any]]:
    """The published view: what the bots looked for, most-asked first, and whether a research run has covered it."""
    now = now or datetime.now(UTC)
    ms = store.markets()
    tried = {f.key for f in store.gap_fills() if not f.ok}
    rows = []
    for c in clusters(now)[:n]:
        status = "filled" if c.filled_at else ("tried" if c.key in tried else "open")
        rows.append({"topic": c.topic, "asks": c.asks, "why": c.why, "last": c.last_at[:10], "status": status, "filled": c.filled_at[:10],
                     "markets": [{"market_id": m, "question": ms[m].question if m in ms else ""} for m in c.markets[:4]]})
    return rows


def spent_today(now: datetime) -> float:
    return round(sum(f.usd for f in store.gap_fills() if f.day == now.date().isoformat()), 6)


def gap_vector(topic: str, why: str) -> dict[str, Any]:
    """The research vector for one gap: a thesis-free brief (what to find out), stamped ``requested_by: markets`` and capped per run."""
    slug = re.sub(r"[^a-z0-9]+", "_", topic.casefold()).strip("_")[:48]
    return {"id": f"gap_{slug}", "title": topic[:180], "thesis": why or topic, "vector_type": "story", "research_effort": "standard",
            "rationale": "Requested by the prediction-market bots: their corpus search found too little on this. Ground it in sources; say plainly what could not be found.",
            "supporting_hits": [], "pillars": [], "scope": [], "key_questions": [], "sources": [], "requested_by": "markets", "cost_cap_usd": flags.GAP_FILL_RUN_CAP_USD}


def subprocess_runner(topic: str, why: str) -> dict[str, Any]:
    """The default fill: one ``signal_profile`` research run (the existing profile pipeline: web research -> profile store -> corpus index on its next
    build), in a child process under its own USD cap. The profile is stamped ``requested_by: markets``."""
    cmd = [sys.executable, "-m", "algent_backend.cli", "runs", "start", "signal_profile", "--input", json.dumps({"vector": gap_vector(topic, why)}), "--foreground"]
    try:
        p = subprocess.run(cmd, capture_output=True, text=True, timeout=2400, check=False)  # noqa: S603 - fixed argv, our own interpreter
    except (OSError, subprocess.TimeoutExpired) as exc:
        return {"ok": False, "note": f"{type(exc).__name__}: {str(exc)[:120]}"}
    return {"ok": p.returncode == 0, "note": "" if p.returncode == 0 else f"exit {p.returncode}: {(p.stderr or p.stdout)[-160:].strip()}",
            "profile_id": _profile_id(topic, why, p.stdout or "") if p.returncode == 0 else ""}


def _profile_id(topic: str, why: str, out: str) -> str:
    """The profile a run produced: the id the run printed if any, else the one its vector determines (``assembly.profile_id_for``; gap_loop re-checks it against the store)."""
    m = re.search(r"""["']?profile_id["']?\s*[:=]\s*["']?(prof_[A-Za-z0-9_\-]+)""", out)
    if m:
        return m.group(1)
    from algent_backend.agent_system.agents.research.assembly import profile_id_for       # lazy: the research agent is a heavy import
    return profile_id_for(gap_vector(topic, why))


def fill(*, now: datetime | None = None, runner: Runner | None = None, limit: int | None = None) -> dict[str, Any]:
    """The daily capped job. Returns a report; never raises for a failed run."""
    now = now or datetime.now(UTC)
    report: dict[str, Any] = {"as_of": now.isoformat(timespec="seconds"), "ran": 0, "ok": 0, "usd": 0.0, "stopped": "", "topics": []}
    if not flags.GAP_FILL_ENABLED:
        return {**report, "stopped": "gap filling is switched off (markets/flags.GAP_FILL_ENABLED)"}
    spent = spent_today(now)
    runs_today = sum(f.day == now.date().isoformat() for f in store.gap_fills())
    refill = timedelta(days=flags.GAP_REFILL_DAYS)
    failed = [tokens(f.topic) for f in store.gap_fills() if not f.ok and (store.parse_iso(f.at) or now) >= now - refill]     # twice failed = parked until the window passes
    cands = [c for c in clusters(now) if not c.filled_at and c.asks >= flags.GAP_MIN_ASKS and sum(_same(c.toks, t) for t in failed) < 2]
    from . import gap_loop                                  # lazy: gap_loop reads this module
    cands = sorted([*cands, *gap_loop.refill_candidates(now)], key=lambda c: (c.asks, c.last_at), reverse=True)
    if flags.GAP_ROUTE_SKIP_FILLS:                          # a free feed answers it, or nothing can yet: do not pay (skips use no cap; the reason is on the report)
        from . import gap_router
        routed = list(zip(cands, gap_router.route_clusters(cands, now)))
        report["skipped"] = [{"topic": c.topic, "asks": c.asks, "route": r.route, "reason": r.skip_reason()} for c, r in routed if r.skip_reason()]
        cands = [c for c, r in routed if not r.skip_reason()]
    report["candidates"] = len(cands)
    runner = runner or subprocess_runner
    cap = flags.GAP_FILL_MAX_PER_DAY if limit is None else min(limit, flags.GAP_FILL_MAX_PER_DAY)
    for c in cands:
        if runs_today >= cap:
            report["stopped"] = f"run limit reached ({runs_today} today)"
            break
        if spent + flags.GAP_FILL_EST_USD > flags.GAP_FILL_USD_PER_DAY + 1e-9:
            report["stopped"] = f"day budget reached (${spent:.2f} of ${flags.GAP_FILL_USD_PER_DAY:.2f})"
            break
        why = c.why + (f" Asked for by prediction-market questions such as: {c.questions[0]}" if c.questions else "")
        res = runner(c.topic, why.strip())
        at = datetime.now(UTC).isoformat(timespec="seconds") if now is None else now.isoformat(timespec="seconds")
        usd = float(res.get("usd") or flags.GAP_FILL_EST_USD)
        store.append_gap_fills([GapFill(id=gap_id("fill", c.key, at), at=at, day=at[:10], key=c.key, topic=c.topic, asks=c.asks, markets=c.markets[:8],
                                        ok=bool(res.get("ok")), usd=round(usd, 4), note=str(res.get("note", ""))[:200],
                                        profile_id=str(res.get("profile_id") or "") if res.get("ok") else "", refill=c.refill)])
        spent, runs_today = spent + usd, runs_today + 1
        report["ran"] += 1
        report["ok"] += bool(res.get("ok"))
        report["usd"] = round(report["usd"] + usd, 4)
        report["topics"].append({"topic": c.topic, "asks": c.asks, "ok": bool(res.get("ok")), "refill": c.refill})
    return report
