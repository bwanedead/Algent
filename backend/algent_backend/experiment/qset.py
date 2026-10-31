"""
The common question set: a mandatory, versioned set of resolved questions every protocol answers, so no protocol wins by choosing easy ones (framework section 5).

``build`` assembles it from resolved markets already in the markets store: one market per event (siblings are not independent questions), a fixed cutoff
``hours_before`` before resolution, a price on file at that cutoff, and topics taken round-robin so one theme cannot fill the set. It is stored write-once under
``sets/<id>/set.json`` (id = digest of its content) and appended to ``sets/index.jsonl``, so every version stays and "latest" is the last line.

Set version 2 (``hours_list``, CLI ``--multi``): the same market may contribute a question at several cutoffs (e.g. 168, 48 and 12 hours before resolution), each only
when a price is on file at that cutoff. The market stays the unit of independence (still one market per event family), so a standard error over questions is optimistic;
the set records ``n_markets`` beside the question count. Old sets are untouched: their params, and so their ids, do not change.

``run`` answers it in controlled mode: for each question ONE snapshot, then every named protocol on that snapshot. Spend is bounded by a TOTAL cap for the invocation
(``flags.SET_RUN_CAP_USD``) on top of the per-call caps under the budget gate; when the cap is reached the rest is reported as not run, and running again continues
(a finished run is never repeated).
"""

from __future__ import annotations

from datetime import timedelta
from typing import Any

from . import branches, controls, flags, minds, policies, runner, score, sources, store
from .contracts import Branch, Protocol, Question


def _topic(m: Any) -> str:
    return (m.theaters[0] if m.theaters else (m.tags[0] if m.tags else "other")).lower()


def _unclashed(q: Question) -> Question:
    """A question stored earlier under this id with different content (e.g. made before the reference price was read in time order) stays as it was: this one gets a new id."""
    old = store.read_json(f"questions/{q.id}.json")
    if old is not None and store.canonical(old) != store.canonical(q):
        return q.model_copy(update={"id": f"{q.id}-p{store.digest(q)[:4]}"})
    return q


def plan(*, min_n: int = flags.SET_MIN_QUESTIONS, max_n: int | None = None, hours_before: float = flags.SET_HOURS_BEFORE, hours_list: tuple[float, ...] | None = None) -> dict[str, Any]:
    """What ``build`` would store, without storing anything (the CLI dry run prints this). One market per event family; with ``hours_list`` (set version 2) a market
    contributes one question at EACH listed number of hours before resolution that has a price on file, so one market can give several questions; the event family
    stays the unit of independence (two markets of one event never both enter). ``max_n`` defaults to ``flags.SET_MAX_QUESTIONS`` for a single cutoff and to
    "every qualifying question" for several."""
    from algent_backend.markets import store as ms

    multi = hours_list is not None
    cutoffs_h = tuple(hours_list) if hours_list is not None else (hours_before,)
    if max_n is None and not multi:
        max_n = flags.SET_MAX_QUESTIONS
    skipped = {"no_price_at_cutoff": 0, "same_event": 0, "bad_cutoff": 0, "duplicate_question": 0}
    markets = ms.markets()
    resolved = sorted((m for m in markets.values() if m.status == "resolved" and m.outcome in ("yes", "no")), key=lambda m: (m.resolved_at, m.id), reverse=True)
    snaps = ms.snapshots_by_market()
    families: dict[str, list[tuple[Any, list[Question]]]] = {}           # event family -> its markets with at least one priced cutoff, recency order
    for m in resolved:
        end = store.parse_time(m.resolved_at)
        if end is None:
            skipped["bad_cutoff"] += 1
            continue
        qs: list[Question] = []
        for h in cutoffs_h:
            cutoff = (end - timedelta(hours=h)).isoformat(timespec="seconds")
            if ms.price_at(sorted(snaps.get(m.id, []), key=lambda s: s.at), cutoff) is None:
                skipped["no_price_at_cutoff"] += 1
                continue
            try:
                qs.append(_unclashed(sources.question_from_market(m.id, cutoff).model_copy(update={"common_set": True})))
            except (KeyError, ValueError):
                skipped["bad_cutoff"] += 1
        if qs:
            families.setdefault(m.event_id or f"market:{m.id}", []).append((m, qs))
    cands: dict[str, list[list[Question]]] = {}
    for fam in families.values():
        best = max(fam, key=lambda mq: len(mq[1])) if multi else fam[0]      # one cutoff keeps the old pick (most recent priced); several prefer the market covering most cutoffs
        skipped["same_event"] += len(fam) - 1
        cands.setdefault(_topic(best[0]), []).append(best[1])
    for lst in cands.values():
        lst.sort(key=lambda qs: markets[qs[0].source.split(":", 1)[1]].resolved_at, reverse=True)
    chosen: list[Question] = []
    topics, seen_ids = sorted(cands), set()
    while any(cands.values()) and (max_n is None or len(chosen) < max_n):
        for t in topics:
            if cands[t] and (max_n is None or len(chosen) < max_n):
                for q in cands[t].pop(0):
                    if q.id in seen_ids:
                        skipped["duplicate_question"] += 1
                    elif max_n is None or len(chosen) < max_n:
                        seen_ids.add(q.id)
                        chosen.append(q)
    by_topic: dict[str, int] = {}
    by_hours: dict[str, int] = {}
    entries = []
    for q in chosen:
        mid = q.source.split(":", 1)[1]
        t = _topic(markets[mid])
        by_topic[t] = by_topic.get(t, 0) + 1
        end, cut = store.parse_time(markets[mid].resolved_at), store.parse_time(q.cutoff)
        if end is not None and cut is not None:
            key = f"{(end - cut).total_seconds() / 3600:g}"
            by_hours[key] = by_hours.get(key, 0) + 1
        entries.append({"id": q.id, "cutoff": q.cutoff, "source": q.source, "topic": t})
    params: dict[str, Any] = {"min_n": min_n, "max_n": max_n, "hours_before": hours_before}
    if multi:                                                              # set version 2: old sets keep exactly their old params, and so their ids
        params = {"min_n": min_n, "max_n": max_n, "hours_list": list(cutoffs_h), "set_version": 2}
    return {"chosen": chosen, "entries": entries, "params": params, "topics": by_topic, "by_hours_before": by_hours, "skipped": skipped, "short_of_target": len(chosen) < min_n,
            "n_markets": len({e["source"] for e in entries}), "n_resolved_markets": len(resolved), "n_event_families": len(families)}


def build(*, min_n: int = flags.SET_MIN_QUESTIONS, max_n: int | None = None, hours_before: float = flags.SET_HOURS_BEFORE, hours_list: tuple[float, ...] | None = None,
          dry_run: bool = False) -> dict[str, Any]:
    """Store the set (write-once, versioned by content) and return it; ``dry_run`` returns what would be stored and writes nothing."""
    p = plan(min_n=min_n, max_n=max_n, hours_before=hours_before, hours_list=hours_list)
    sid = store.digest({"entries": p["entries"], "params": p["params"]})[:10]
    doc: dict[str, Any] = {"id": sid, "built_at": store.now_iso(), "params": p["params"], "questions": p["entries"], "topics": p["topics"], "skipped": p["skipped"],
                           "short_of_target": p["short_of_target"],
                           "note": "a common set is mandatory for every protocol; it is built from resolved markets only, one per event, at a fixed cutoff before resolution"}
    if hours_list is not None:
        doc.update(by_hours_before=p["by_hours_before"], n_markets=p["n_markets"], n_resolved_markets=p["n_resolved_markets"], n_event_families=p["n_event_families"],
                   note="set version 2: one market per event family, several cutoffs per market (each with a price on file); the market is the unit of independence, not the question")
    if dry_run:
        return {**doc, "dry_run": True, "stored": False}
    for q in p["chosen"]:
        runner.save_question(q)
    if not store.exists(f"sets/{sid}/set.json"):
        store.write_once(f"sets/{sid}/set.json", doc)
        store.append("sets/index.jsonl", {"id": sid, "built_at": doc["built_at"], "n": len(p["chosen"])})
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


NAMED = {"p0": policies.freeze_blind_forecaster, "p0b": controls.freeze_production_research, "p0b+prior": minds.freeze_prior, "b": minds.freeze_delineation, "b+prior": minds.freeze_combined}


def protocol_named(name: str) -> Protocol:
    """A named control or mind (``p0``, ``p0b``, ``p0b+prior``, ``b``) or a protocol id stored in the lab."""
    return NAMED[name]() if name in NAMED else policies.load_protocol(name)


def max_cost(proto: Protocol) -> float:
    """Upper bound of one run's spend: the forecast call cap plus, for a planning evidence policy, its planner caps."""
    pv = proto.policies["evidence"]
    plan = float(pv.params.get("plan_cap_usd", 0.0)) * int(pv.params.get("max_rounds", 0)) if policies.is_planned(pv) else 0.0
    return round(flags.RUN_CAP_USD + plan, 4)


def run(doc: dict[str, Any], names: list[str], source: Any, ask_for: Any, *, live: bool, cap_usd: float = flags.SET_RUN_CAP_USD, plan_ask_for: Any = None,
        corpus: Any = None, aware_ask_for: Any = None) -> dict[str, Any]:
    """Every named protocol on every question of the set, controlled. A run already on disk is reused and costs nothing. With ``aware_ask_for`` each finished run
    also gets its market-aware second output (``minds.run_aware``), once, counted against the same cap."""
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
                spent, stopped = _aware(rid, q, b, aware_ask_for, live, spent, cap_usd, stopped, done, pending, name)
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
            spent, stopped = _aware(rec.run_id, q, b, aware_ask_for, live, spent, cap_usd, stopped, done, pending, name)
    return {"set": doc["id"], "live": live, "protocols": {n: p.id for n, p in protos}, "ran": done, "reused": reused, "spent_usd": round(spent, 4), "cap_usd": cap_usd,
            "not_run": pending, "max_usd_if_all_pending_run": round(sum(p["max_usd"] for p in pending), 4), "stopped": stopped}


def _aware(rid: str, q: Question, b: Branch, aware_ask_for: Any, live: bool, spent: float, cap: float, stopped: str, done: list, pending: list, name: str) -> tuple[float, str]:
    """The optional market-aware step for one finished run; skipped when already stored, when there is no reference price, or when the cap would be exceeded."""
    if aware_ask_for is None or store.exists(f"runs/{rid}/aware.json") or q.reference.get("market_p") is None or (store.read_json(f"runs/{rid}/run.json") or {}).get("p") is None:
        return spent, stopped
    if not live or stopped or spent + flags.RUN_CAP_USD > cap:
        pending.append({"question": q.id, "protocol": name, "stage": "aware", "max_usd": flags.RUN_CAP_USD})
        return spent, stopped or ("" if not live else f"the ${cap:.2f} set cap would be exceeded by the next run (spent ${spent:.3f})")
    doc = minds.run_aware(rid, q, aware_ask_for(policies.load_protocol(b.protocol_id)))
    if doc:
        done.append({"question": q.id, "protocol": name, "run": rid, "stage": "aware", "p": doc["p"], "usd": doc["usd"]})
        spent += doc["usd"]
    return spent, stopped


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
