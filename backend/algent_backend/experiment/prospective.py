"""
The prospective lab: the data-volume fix. The historical set (qset.py) is small because few markets have resolved with a price on file; a prospective question is about a
LIVE market, asked and answered today, and scored whenever the market resolves. Nothing here needs hindsight: the cutoff is the moment of asking.

Each day ``build`` picks up to ``flags.PROSPECTIVE_MARKETS`` markets from the markets store that are open, CONTESTED (YES price inside ``markets.flags.CONTESTED_LO..HI``,
read from a fresh snapshot), pass the mirror's liquidity and volume floors, resolve between ``PROSPECTIVE_MIN_H`` and ``PROSPECTIVE_MAX_H`` hours from now, are not asked
before, one per event family, topics round-robin (qset's helpers). Each becomes a question with cutoff = now, built by ``sources.question_from_market`` exactly like a qset
question (the YES price at the cutoff is stored as the market reference, which no protocol sees). The day's questions are one question-set version, appended to
``sets/prospective.jsonl`` (a separate index, so ``--set latest`` stays the historical set); ``--set prospective`` is every daily version together (``load``).

``run`` has every ACTIVE protocol (a controlled protocol with stored runs that is not retired) forecast each of today's questions through the ordinary runner, blind, under
the day's hard budget ``PROSPECTIVE_USD_PER_DAY``: an estimate of the next call is checked BEFORE it and the first one that would not fit stops the day cleanly (the log line says
how far it got). Question-major order keeps the protocols paired (each question is answered by all of them before the next starts); the protocol order and the question order
both rotate with the date, so a budget cut does not always starve the same protocol or the same question. A run on disk is reused for free. The results are ordinary stored runs:
``lab score``, ``lab calibrate``, ``lab block`` and the tournament pick them up once the markets resolve.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from algent_backend.markets import flags as mf
from algent_backend.markets import store as ms

from . import branches, flags, genealogy, policies, qset, runner, score, sources, store

INDEX = "sets/prospective.jsonl"
LOG = "prospective/log.jsonl"


def _family(m: Any) -> str:
    return m.event_id or f"market:{m.id}"


def asked_markets() -> set[str]:
    """Market ids already asked in any prospective version (a market is asked once: its resolution is one outcome, not one per day)."""
    return {e["source"].split(":", 1)[1] for sid in {r["id"] for r in store.read_lines(INDEX)} for e in (store.read_json(f"sets/{sid}/set.json") or {}).get("questions", [])}


def _asked_today(day: str) -> int:
    return sum(r.get("n", 0) for r in store.read_lines(INDEX) if r.get("day") == day)


def select(now: datetime, *, limit: int | None = None) -> tuple[list[Any], dict[str, int]]:
    """The markets to ask about at ``now`` (best first by topic round-robin) and why others were left out. Free; stores nothing."""
    limit = flags.PROSPECTIVE_MARKETS if limit is None else limit
    skipped = {"not_open": 0, "thin": 0, "horizon": 0, "no_fresh_price": 0, "not_contested": 0, "already_asked": 0, "same_event": 0}
    asked, snaps, at = asked_markets(), ms.snapshots_by_market(), now.isoformat(timespec="seconds")
    families: dict[str, tuple[Any, float]] = {}
    for m in sorted(ms.markets().values(), key=lambda m: (-m.liquidity, m.id)):
        end = store.parse_time(m.end_date)
        hours = (end - now).total_seconds() / 3600 if end is not None else None
        snap = ms.price_at(snaps.get(m.id, []), at, max_age_h=mf.PRICE_FRESH_H)
        if m.status != "open":
            skipped["not_open"] += 1
        elif m.liquidity < mf.MIN_LIQUIDITY_USD or m.volume < mf.MIN_VOLUME_USD:
            skipped["thin"] += 1
        elif hours is None or not flags.PROSPECTIVE_MIN_H <= hours <= flags.PROSPECTIVE_MAX_H:
            skipped["horizon"] += 1
        elif snap is None:
            skipped["no_fresh_price"] += 1
        elif not mf.CONTESTED_LO <= snap.p <= mf.CONTESTED_HI:
            skipped["not_contested"] += 1
        elif m.id in asked:
            skipped["already_asked"] += 1
        elif _family(m) in families:
            skipped["same_event"] += 1                                       # the list is liquidity-first, so the family's deepest market was taken
        else:
            families[_family(m)] = (m, snap.p)
    by_topic: dict[str, list[Any]] = {}
    for m, _ in families.values():
        by_topic.setdefault(qset.topic(m), []).append(m)
    return qset.round_robin(by_topic, limit), skipped


def plan(now: datetime | None = None) -> dict[str, Any]:
    """What ``build`` would store now (nothing is written): the chosen markets, today's remaining quota and the reasons for the rest."""
    now = now or datetime.now(UTC)
    day = now.date().isoformat()
    left = max(0, flags.PROSPECTIVE_MARKETS - _asked_today(day))
    chosen, skipped = select(now, limit=left)
    return {"day": day, "at": now.isoformat(timespec="seconds"), "quota_left": left, "chosen": chosen, "skipped": skipped}


def build(now: datetime | None = None, *, dry_run: bool = False) -> dict[str, Any]:
    """Store today's new questions as one prospective set version and return it (``n`` = 0 when nothing qualified). ``dry_run`` stores nothing."""
    p = plan(now)
    cutoff = p["at"]
    qs = [sources.question_from_market(m.id, cutoff).model_copy(update={"common_set": True}) for m in p["chosen"]]
    entries = [{"id": q.id, "cutoff": q.cutoff, "source": q.source, "topic": qset.topic(m)} for q, m in zip(qs, p["chosen"], strict=True)]
    params = {"kind": "prospective", "day": p["day"], "at": cutoff, "max_n": flags.PROSPECTIVE_MARKETS, "min_h": flags.PROSPECTIVE_MIN_H, "max_h": flags.PROSPECTIVE_MAX_H}
    sid = store.digest({"entries": entries, "params": params})[:10]
    doc = {"id": sid, "built_at": store.now_iso(), "params": params, "questions": entries, "skipped": p["skipped"], "quota_left": p["quota_left"],
           "note": "prospective: live contested markets asked at their cutoff (= now); every active protocol answers blind; scored when the market resolves"}
    if dry_run or not qs:
        return {**doc, "dry_run": dry_run, "stored": False}
    for q in qs:
        runner.save_question(q)
    if not store.exists(f"sets/{sid}/set.json"):
        store.write_once(f"sets/{sid}/set.json", doc)
        store.append(INDEX, {"id": sid, "day": p["day"], "built_at": doc["built_at"], "n": len(qs)})
    return {**doc, "stored": True}


def load(day: str = "") -> dict[str, Any]:
    """Every prospective version together as one set (id ``prospective``), or only that day's questions. KeyError when none has been built."""
    ids = [r["id"] for r in store.read_lines(INDEX) if not day or r.get("day") == day]
    if not ids:
        raise KeyError("no prospective question set built yet: newsroom lab prospective --live")
    seen: set[str] = set()
    entries = []
    for sid in dict.fromkeys(ids):
        for e in (store.read_json(f"sets/{sid}/set.json") or {}).get("questions", []):
            if e["id"] not in seen:
                seen.add(e["id"])
                entries.append(e)
    return {"id": "prospective", "params": {"kind": "prospective", "day": day}, "questions": entries, "versions": len(set(ids))}


# ── the day's forecasts ──────────────────────────────────────────────────────────────────────────
def active_protocols() -> list[str]:
    """Ids of the controlled protocols that have stored runs and are not retired, in a stable order."""
    ran = {r.protocol_id for r in score.runs() if r.mode == "controlled"}
    return sorted(pid for pid in genealogy.all_protocols() if pid in ran and not store.exists(f"retired/{pid}.json"))


def estimate(pid: str, stored: dict[str, list[float]] | None = None) -> float:
    """What one more run of the protocol is expected to cost: the mean of its stored runs once there are enough of them, else the most one run can cost."""
    costs = (stored if stored is not None else _stored_costs()).get(pid, [])
    if len(costs) >= flags.PROSPECTIVE_MIN_RUNS_FOR_MEAN and sum(costs) > 0:
        return sum(costs) / len(costs)
    return qset.max_cost(policies.load_protocol(pid))


def _stored_costs() -> dict[str, list[float]]:
    out: dict[str, list[float]] = {}
    for r in score.runs():
        if r.mode == "controlled" and r.usd > 0:
            out.setdefault(r.protocol_id, []).append(r.usd)
    return out


def spent_today(day: str) -> float:
    return round(sum(r.get("spent_usd", 0.0) for r in store.read_lines(LOG) if r.get("day") == day), 6)


def rotate(items: list[Any], day: str) -> list[Any]:
    """The list started at a position that moves with the date, so a cut-off day does not always drop the same tail."""
    if not items:
        return items
    k = datetime.fromisoformat(day).toordinal() % len(items)
    return items[k:] + items[:k]


def run(day: str, source: Any, ask_for: Any, *, budget_usd: float = flags.PROSPECTIVE_USD_PER_DAY, plan_ask_for: Any = None, corpus: Any = None) -> dict[str, Any]:
    """Every active protocol on every question of ``day`` (live: it calls the model), paired, under the day's budget; the first call that would not fit stops it. Logs how far it got."""
    pids = rotate(active_protocols(), day)
    try:
        qs = rotate(qset.questions_of(load(day)), day)
    except KeyError:
        qs = []
    costs = _stored_costs()
    est = {pid: estimate(pid, costs) for pid in pids}
    already = spent_today(day)
    spent, ran, reused, stopped, pending = 0.0, [], 0, "", 0
    sids: dict[str, str] = {}                                          # one snapshot per cutoff: the day's questions share it
    for q in qs:
        if stopped:
            pending += len(pids)
            continue
        sid = sids.get(q.cutoff) or sids.setdefault(q.cutoff, runner.build_snapshot(source, q)[0])
        for pid in pids:
            if stopped:
                pending += 1
            elif store.exists(f"runs/{runner.run_id_for(q, pid, sid)}/run.json"):
                reused += 1
            elif already + spent + est[pid] > budget_usd:
                stopped = f"the ${budget_usd:.2f} day budget would be exceeded by the next call (spent ${already + spent:.3f}, next about ${est[pid]:.3f})"
                pending += 1
            else:
                proto = policies.load_protocol(pid)
                pa = plan_ask_for(proto.policies["evidence"]) if plan_ask_for and policies.is_planned(proto.policies["evidence"]) else None
                rec = runner.run_branch(q, branches.ensure(proto.name, proto), sid, ask_for(proto), live=True, plan_ask=pa, corpus=corpus)
                spent += rec.usd
                ran.append({"question": q.id, "protocol": pid, "run": rec.run_id, "p": rec.p, "usd": rec.usd})
    out = {"day": day, "questions": len(qs), "protocols": pids, "ran": ran, "reused": reused, "not_run": pending, "spent_usd": round(spent, 4),
           "spent_earlier_today_usd": already, "budget_usd": budget_usd, "stopped": stopped}
    store.append(LOG, {**{k: out[k] for k in ("day", "questions", "reused", "not_run", "spent_usd", "budget_usd", "stopped", "protocols")}, "ran": len(ran), "at": store.now_iso()})
    return out


def run_day(now: datetime | None = None, *, source: Any, ask_for: Any, live: bool, plan_ask_for: Any = None, corpus: Any = None,
            budget_usd: float = flags.PROSPECTIVE_USD_PER_DAY) -> dict[str, Any]:
    """The whole daily job: store today's questions (live only), then have the protocols forecast them. Without ``live``: the plan and the maximum cost, nothing stored or called."""
    now = now or datetime.now(UTC)
    built = build(now, dry_run=not live)
    day = now.date().isoformat()
    if not live:
        return {"live": False, "day": day, "would_ask": built["questions"], "skipped": built["skipped"], "quota_left": built["quota_left"],
                "protocols": active_protocols(), "estimate_per_run_usd": {pid: round(estimate(pid), 4) for pid in active_protocols()},
                "budget_usd": budget_usd, "note": "add --live to store the questions and spend (at most the day budget)"}
    out = run(day, source, ask_for, budget_usd=budget_usd, plan_ask_for=plan_ask_for, corpus=corpus)
    return {**out, "new_questions": len(built["questions"]) if built.get("stored") else 0, "skipped": built["skipped"], "quota_left": built["quota_left"]}
