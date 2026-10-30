"""
Did the research help? The read-only check that closes the gap loop (bots ask -> ``gaps.fill`` researches -> the profile joins the corpus -> ...). For
each successful fill it links the profile the run produced, then counts what the bots did with it afterwards:

* re-asks: gaps on the same cluster (``gaps.tokens`` Jaccard, the rule that clusters asks) recorded after the fill, against before;
* uptake: later traces that RETURNED the profile (or a claim / timeline row of it) and later forecasts / decisions that CITED it, on any market;
* evidence ratings (sufficient / thin / gap) on the fill's markets plus every market that asked the cluster, before vs after;
* accuracy: on markets the bot forecast both before and after, the bot's edge over the market price (market Brier - bot Brier), each side shown ONLY
  once it holds ``flags.MIN_RESOLVED_FOR_VERDICT`` resolved forecasts.

Verdict per fill: "asked again" (``LOOP_REASK_MIN``+ re-asks), "answered" (cited), "unlinked" (no profile found for the run), "too early" (younger than
``LOOP_SETTLE_DAYS`` or nothing since on its markets), else "unused". ``refill_candidates`` hands "asked again" clusters back to ``gaps.fill`` ONCE.

Limits, stated on the page: a market asks a topic once (``gaps.record`` dedupes), so only OTHER markets can re-ask; traces are pruned by age, so
"returned" is a floor while "cited" (on the forecast / decision lines) is not.
"""

from __future__ import annotations

import json
from collections import Counter
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from typing import Any

from . import flags, gaps, store
from .contracts import BotForecast, Gap, GapFill, Trace

_LINK_FROM, _LINK_TO = timedelta(hours=-1), timedelta(hours=6)       # a run's profile is written after the fill's job started (``GapFill.at`` is the job's start)
_PROFILE_FIELDS = ("id", "title", "requested_by", "generated_at")


@dataclass
class _Call:
    """A forecast or a trade decision, whichever bot said it: what it rated and cited."""
    id: str
    market_id: str
    at: str
    evidence: str
    cited: list[str]


@dataclass
class Facts:
    gaps: list[Gap] = field(default_factory=list)
    fills: list[GapFill] = field(default_factory=list)
    calls: list[_Call] = field(default_factory=list)
    traces: list[Trace] = field(default_factory=list)
    bots: list[BotForecast] = field(default_factory=list)
    outcomes: dict[str, str] = field(default_factory=dict)          # market id -> yes | no, resolved only
    profiles: list[dict[str, str]] = field(default_factory=list)


def _profiles() -> list[dict[str, str]]:
    """The profile store's headers only (id, title, requested_by, generated_at); [] when there is none."""
    try:
        from algent_backend.agent_system.agents.research.store import JsonProfileStore
        root = JsonProfileStore().root
        paths = sorted(root.glob("*.json")) if root.is_dir() else []
    except Exception:  # noqa: BLE001 - a missing store only means "cannot link by search"
        return []
    out = []
    for path in paths:
        try:
            d = json.loads(path.read_text(encoding="utf-8"))
            out.append({k: str(d.get(k) or "") for k in _PROFILE_FIELDS})
        except (OSError, ValueError, AttributeError):
            continue
    return out


def load(profiles: list[dict[str, str]] | None = None) -> Facts:
    ms = store.markets()
    return Facts(gaps=store.gaps(), fills=sorted(store.gap_fills(), key=lambda f: f.at), traces=store.traces(), bots=store.bot_forecasts(),
                 calls=[*(_Call(f.id, f.market_id, f.made_at, f.evidence, f.evidence_ids) for f in store.forecasts()),
                        *(_Call(d.id, d.market_id, d.at, d.evidence, d.evidence_ids) for d in store.decisions(None) if d.action != "settle")],
                 outcomes={k: m.outcome for k, m in ms.items() if m.status == "resolved" and m.outcome in ("yes", "no")},
                 profiles=_profiles() if profiles is None else profiles)


def link(f: GapFill, profiles: list[dict[str, str]]) -> str:
    """The profile id a fill produced: the id recorded on the line (when the store, if readable, holds it), else the markets-requested profile written
    inside the run's time window whose title matches the topic (older lines have no id). "" = unlinked."""
    if f.profile_id and (not profiles or any(p["id"] == f.profile_id for p in profiles)):
        return f.profile_id
    at, toks = store.parse_iso(f.at), gaps.tokens(f.topic)
    near: list[tuple[float, str]] = []
    for p in profiles:
        g = store.parse_iso(p["generated_at"]) if p["requested_by"] == "markets" else None
        if g is not None and at is not None and _LINK_FROM <= g - at <= _LINK_TO and gaps._same(toks, gaps.tokens(p["title"])):
            near.append((abs((g - at).total_seconds()), p["id"]))
    return min(near)[1] if near else ""


def _ours(corpus_id: str, pid: str) -> bool:
    """Corpus ids that come from one profile (``corpus/sources/profiles.py``): the document, its claims, its timeline events."""
    return corpus_id == f"profile:{pid}" or corpus_id.startswith((f"claim:{pid}:", f"profile-timeline:{pid}:"))


def _tally(calls: list[_Call]) -> dict[str, int]:
    c = Counter(x.evidence for x in calls if x.evidence)
    return {"rated": sum(c.values()), "sufficient": c["sufficient"], "thin": c["thin"], "gap": c["gap"]}


def _edge(bots: list[BotForecast], outcomes: dict[str, str], cut: str, end: str) -> dict[str, Any]:
    """Market Brier minus bot Brier on resolved forecasts of markets forecast on both sides of the fill; each side withheld below the verdict minimum."""
    from .bot_forecasts import brier
    pre = [b for b in bots if b.at < cut]
    post = [b for b in bots if cut < b.at < end]
    both = {b.market_id for b in pre} & {b.market_id for b in post}

    def side(rows: list[BotForecast]) -> tuple[int, float | None]:
        got = [(brier(b.p, 1 if outcomes[b.market_id] == "yes" else 0), brier(b.market, 1 if outcomes[b.market_id] == "yes" else 0))
               for b in rows if b.market_id in both and b.market_id in outcomes and b.market is not None]
        return len(got), (sum(m - o for o, m in got) / len(got) if got else None)

    (nb, eb), (na, ea), need = side(pre), side(post), flags.MIN_RESOLVED_FOR_VERDICT
    shown = nb >= need and na >= need
    return {"shown": shown, "min": need, "n_before": nb, "n_after": na, "before": round(eb, 4) if shown and eb is not None else None,
            "after": round(ea, 4) if shown and ea is not None else None}


def assess(f: GapFill, facts: Facts, now: datetime) -> dict[str, Any]:
    """One fill's row: the link, the before/after counts and the verdict. The "after" window ends at the next run on the same cluster, so a refill is judged on its own."""
    toks, cut = gaps.tokens(f.topic), f.at
    later = [x.at for x in facts.fills if x.at > f.at and gaps._same(toks, gaps.tokens(x.topic))]
    end = min(later, default="9999")
    cluster = [g for g in facts.gaps if gaps._same(toks, gaps.tokens(g.topic))]
    scope = {*f.markets, *(g.market_id for g in cluster)}
    pid = link(f, facts.profiles)
    calls = [c for c in facts.calls if c.market_id in scope]
    after = [c for c in calls if cut < c.at < end]
    reasks = [g for g in cluster if cut < g.at < end]
    out: dict[str, Any] = {"topic": f.topic, "at": f.at[:10], "asks": f.asks, "refill": f.refill, "profile_id": pid, "linked": bool(pid),
                           "reasks_before": sum(g.at < cut for g in cluster), "reasks_after": len(reasks), "returned_after": None, "cited_after": None,
                           "decisions_after": len(after), "evidence_before": _tally([c for c in calls if c.at < cut]), "evidence_after": _tally(after),
                           "edge": _edge([b for b in facts.bots if b.market_id in scope], facts.outcomes, cut, end)}
    cited = returned = 0
    if pid:
        ts = [t for t in facts.traces if cut < t.at < end]
        returned = len({t.ref or t.id for t in ts if any(_ours(i, pid) for i in t.returned_ids)})
        cited = len({*(c.id for c in facts.calls if cut < c.at < end and any(_ours(i, pid) for i in c.cited)),
                     *(t.ref or t.id for t in ts if any(_ours(i, pid) for i in t.cited_ids))})
        out["returned_after"], out["cited_after"] = returned, cited
    young = (store.parse_iso(f.at) or now) > now - timedelta(days=flags.LOOP_SETTLE_DAYS)
    quiet = not after and not any(cut < b.at < end for b in facts.bots if b.market_id in scope)
    out["verdict"] = ("asked again" if len(reasks) >= flags.LOOP_REASK_MIN else "answered" if cited else "unlinked" if not pid
                      else "too early" if young or quiet else "unused")
    return out


def block(now: datetime | None = None, facts: Facts | None = None) -> dict[str, Any]:
    """The published ``loop`` block: totals over every successful fill, the newest ``LOOP_ROWS_SHOWN`` as rows."""
    now = now or datetime.now(UTC)
    facts = facts or load()
    done = [f for f in facts.fills if f.ok]
    rows = [assess(f, facts, now) for f in reversed(done)]
    v = Counter(r["verdict"] for r in rows)
    return {"fills": len(done), "failed": len(facts.fills) - len(done), "answered": v["answered"], "unused": v["unused"], "asked_again": v["asked again"],
            "too_early": v["too early"], "unlinked": v["unlinked"], "usd": round(sum(f.usd for f in facts.fills), 4), "rows": rows[:flags.LOOP_ROWS_SHOWN],
            "min_for_verdict": flags.MIN_RESOLVED_FOR_VERDICT, "settle_days": flags.LOOP_SETTLE_DAYS, "reask_min": flags.LOOP_REASK_MIN,
            "basis": ("Counts from our own ledgers: asks recorded after each research run, the later forecasts and trades that returned or cited its profile, "
                      f"and the bot's edge over the market price on markets it forecast on both sides of the run, shown once each side holds {flags.MIN_RESOLVED_FOR_VERDICT} "
                      "resolved forecasts. A market asks a topic once, so only other markets can ask again; research traces are pruned by age.")}


def _brief(asks: list[Gap]) -> str:
    """What the sharper run is told: the first run left these follow-up asks unanswered."""
    seen: list[str] = []
    for g in asks:
        line = g.topic + (f" ({g.why})" if g.why else "")
        if line not in seen:
            seen.append(line)
    qs = list(dict.fromkeys(g.question for g in asks if g.question))[:2] 
    return ("An earlier research run on this topic did not settle it: the prediction-market bots asked again afterwards. Answer what it left open. Unanswered asks: "
            + "; ".join(seen[:flags.LOOP_REASK_QUOTES]) + "." + (f" Questions they were forecasting: {' | '.join(qs)}" if qs else ""))[:900]


def refill_candidates(now: datetime, facts: Facts | None = None) -> list[gaps.Cluster]:
    """Clusters whose latest successful fill (inside ``GAP_REFILL_DAYS``) was asked again ``LOOP_REASK_MIN``+ times and that never had a refill: ONE more run each,
    with a brief that quotes the re-asks. They compete for the same daily caps as any other fill; nothing here spends."""
    facts = facts or load([])
    window, out = timedelta(days=flags.GAP_REFILL_DAYS), []
    for f in reversed(facts.fills):
        t, toks = store.parse_iso(f.at), gaps.tokens(f.topic)
        family = [x for x in facts.fills if gaps._same(toks, gaps.tokens(x.topic))]
        if not f.ok or t is None or now - t > window or family[-1] is not f or any(x.refill for x in family) or any(gaps._same(toks, c.toks) for c in out):
            continue
        asks = sorted((g for g in facts.gaps if g.at > f.at and gaps._same(toks, gaps.tokens(g.topic))), key=lambda g: g.at)
        if len(asks) >= flags.LOOP_REASK_MIN:
            out.append(gaps.Cluster(topic=f.topic, key=f.key, asks=len(asks), markets=list(dict.fromkeys(g.market_id for g in asks)), why=_brief(asks),
                                    questions=list(dict.fromkeys(g.question for g in asks if g.question)), last_at=asks[-1].at, toks=toks, refill=True))
    return out
