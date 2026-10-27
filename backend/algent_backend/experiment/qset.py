"""
The common question set: a mandatory, versioned set of resolved questions every protocol answers, so no protocol wins by choosing easy ones (framework section 5).

``build`` assembles it from resolved markets already in the markets store: one market per event (siblings are not independent questions), a fixed cutoff
``hours_before`` before resolution, a price on file at that cutoff, and topics taken round-robin so one theme cannot fill the set. It is stored write-once under
``sets/<id>/set.json`` (id = digest of its content) and appended to ``sets/index.jsonl``, so every version stays and "latest" is the last line.

``run`` answers it in controlled mode: for each question ONE snapshot, then every named protocol on that snapshot. Spend is bounded by a TOTAL cap for the invocation
(``flags.SET_RUN_CAP_USD``) on top of the per-call caps under the budget gate; when the cap is reached the rest is reported as not run, and running again continues
(a finished run is never repeated).
"""

from __future__ import annotations

from datetime import timedelta
from typing import Any

from . import branches, controls, flags, policies, runner, score, sources, store
from .contracts import Branch, Protocol, Question


def _topic(m: Any) -> str:
    return (m.theaters[0] if m.theaters else (m.tags[0] if m.tags else "other")).lower()


def build(*, min_n: int = flags.SET_MIN_QUESTIONS, max_n: int = flags.SET_MAX_QUESTIONS, hours_before: float = flags.SET_HOURS_BEFORE) -> dict[str, Any]:
    from algent_backend.markets import store as ms

    cands: dict[str, list[tuple[str, Question]]] = {}
    seen_events: set[str] = set()
    skipped = {"no_price_at_cutoff": 0, "same_event": 0, "bad_cutoff": 0}
    markets = ms.markets()
    resolved = sorted((m for m in markets.values() if m.status == "resolved" and m.outcome in ("yes", "no")), key=lambda m: (m.resolved_at, m.id), reverse=True)
    snaps = ms.snapshots_by_market()
    for m in resolved:
        end = store.parse_time(m.resolved_at)
        if end is None:
            skipped["bad_cutoff"] += 1
            continue
        cutoff = (end - timedelta(hours=hours_before)).isoformat(timespec="seconds")
        if ms.price_at(sorted(snaps.get(m.id, []), key=lambda s: s.at), cutoff) is None:
            skipped["no_price_at_cutoff"] += 1
            continue
        if m.event_id and m.event_id in seen_events:
            skipped["same_event"] += 1
            continue
        seen_events.add(m.event_id)
        q = sources.question_from_market(m.id, cutoff).model_copy(update={"common_set": True})
        cands.setdefault(_topic(m), []).append((m.id, q))
    chosen: list[Question] = []
    topics = sorted(cands)
    while len(chosen) < max_n and any(cands.values()):
        for t in topics:
            if cands[t] and len(chosen) < max_n:
                chosen.append(cands[t].pop(0)[1])
    by_topic: dict[str, int] = {}
    entries = []
    for q in chosen:
        mid = q.source.split(":", 1)[1]
        t = _topic(markets[mid])
        by_topic[t] = by_topic.get(t, 0) + 1
        entries.append({"id": q.id, "cutoff": q.cutoff, "source": q.source, "topic": t})
    params = {"min_n": min_n, "max_n": max_n, "hours_before": hours_before}
    sid = store.digest({"entries": entries, "params": params})[:10]
    for q in chosen:
        runner.save_question(q)
    doc = {"id": sid, "built_at": store.now_iso(), "params": params, "questions": entries, "topics": by_topic, "skipped": skipped, "short_of_target": len(chosen) < min_n,
           "note": "a common set is mandatory for every protocol; it is built from resolved markets only, one per event, at a fixed cutoff before resolution"}
    if not store.exists(f"sets/{sid}/set.json"):
        store.write_once(f"sets/{sid}/set.json", doc)
        store.append("sets/index.jsonl", {"id": sid, "built_at": doc["built_at"], "n": len(chosen)})
    return store.read_json(f"sets/{sid}/set.json")


def load(set_id: str) -> dict[str, Any]:
    if set_id in ("", "latest"):
        idx = store.read_lines("sets/index.jsonl")
        if not idx:
            raise KeyError("no question set built yet: newsroom lab questions --set build")
        set_id = idx[-1]["id"]
    doc = store.read_json(f"sets/{set_id}/set.json")
    if doc is None:
        raise KeyError(f"unknown question set {set_id}")
    return doc


def questions_of(doc: dict[str, Any]) -> list[Question]:
    out = []
    for e in doc["questions"]:
        raw = store.read_json(f"questions/{e['id']}.json")
        if raw:
            out.append(Question.model_validate(raw))
    return out


NAMED = {"p0": policies.freeze_blind_forecaster, "p0b": controls.freeze_production_research}


def protocol_named(name: str) -> Protocol:
    """A named control (``p0``, ``p0b``) or a protocol id stored in the lab."""
    return NAMED[name]() if name in NAMED else policies.load_protocol(name)


def max_cost(proto: Protocol) -> float:
    """Upper bound of one run's spend: the forecast call cap plus, for a planning evidence policy, its planner caps."""
    pv = proto.policies["evidence"]
    plan = float(pv.params.get("plan_cap_usd", 0.0)) * int(pv.params.get("max_rounds", 0)) if policies.is_planned(pv) else 0.0
    return round(flags.RUN_CAP_USD + plan, 4)


def run(doc: dict[str, Any], names: list[str], source: Any, ask_for: Any, *, live: bool, cap_usd: float = flags.SET_RUN_CAP_USD, plan_ask_for: Any = None,
        corpus: Any = None) -> dict[str, Any]:
    """Every named protocol on every question of the set, controlled. A run already on disk is reused and costs nothing."""
    protos = [(n, protocol_named(n)) for n in names]
    bs: list[tuple[str, Branch]] = [(n, branches.ensure(n, p)) for n, p in protos]
    spent, done, reused, pending = 0.0, [], 0, []
    stopped = ""
    for q in questions_of(doc):
        sid, _, meta = runner.build_snapshot(source, q)
        for name, b in bs:
            rid = runner.run_id_for(q, b.protocol_id, sid)
            if store.exists(f"runs/{rid}/run.json"):
                reused += 1
                continue
            if not live:
                pending.append({"question": q.id, "protocol": name, "max_usd": max_cost(policies.load_protocol(b.protocol_id))})
                continue
            if stopped or spent + max_cost(policies.load_protocol(b.protocol_id)) > cap_usd:
                stopped = stopped or f"the ${cap_usd:.2f} set cap would be exceeded by the next run (spent ${spent:.3f})"
                pending.append({"question": q.id, "protocol": name, "max_usd": max_cost(policies.load_protocol(b.protocol_id))})
                continue
            proto = policies.load_protocol(b.protocol_id)
            pa = plan_ask_for(proto.policies["evidence"]) if plan_ask_for and policies.is_planned(proto.policies["evidence"]) else None
            rec = runner.run_branch(q, b, sid, ask_for(proto), live=True, plan_ask=pa, corpus=corpus)
            spent += rec.usd
            done.append({"question": q.id, "protocol": name, "run": rec.run_id, "p": rec.p, "usd": rec.usd})
    return {"set": doc["id"], "live": live, "protocols": {n: p.id for n, p in protos}, "ran": done, "reused": reused, "spent_usd": round(spent, 4), "cap_usd": cap_usd,
            "not_run": pending, "max_usd_if_all_pending_run": round(sum(p["max_usd"] for p in pending), 4), "stopped": stopped}


def board(doc: dict[str, Any]) -> dict[str, Any]:
    """The controlled scoreboard restricted to this set's questions: per protocol Brier and log (with standard errors), abstentions and cost; paired differences
    with standard errors over the questions both answered; and how much of the set each protocol covered."""
    ids = {e["id"] for e in doc["questions"]}
    sb = score.scoreboard(only=ids)
    covered: dict[str, int] = {}
    for r in score.runs():
        if r.question_id in ids and r.mode == "controlled":
            covered[r.protocol_id] = covered.get(r.protocol_id, 0) + 1
    ctl = sb["modes"].get("controlled", {"protocols": {}, "differences": {}, "rows": []})
    return {"set": doc["id"], "n_questions": len(ids), "answered_by": covered, "unresolved": sb["unresolved"], "protocols": ctl["protocols"], "differences": ctl["differences"]}
