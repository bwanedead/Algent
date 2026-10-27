"""
Replay integrity audit (``newsroom lab audit RUN``). Reads ONLY what a run stored (question, snapshot, manifest, prompt, branch memory) and, when a corpus index is
given, looks up provenance of corpus rows; it re-derives nothing the run did. For every piece of what the mind saw it lists the event / publish / acquired /
derived times against the cutoff and a verdict:

  ok         proven at or before the cutoff by a time we hold (publish AND ledger acquisition, or a branch's own as-of)
  unproven   nothing contradicts it but nothing proves it either (acquisition unknown, a row with no derivation time, an entity profile stamped as-of by construction)
  LEAK       the stored data shows it postdates the cutoff, or differs from the cutoff-time record

Items audited: evidence shown, derived features (origin chains, recomputed and compared), memory seen, the question text itself (as-of the cutoff revision of the
market), the market reference price (never in the blind prompt), and the code under the run (drift since the freeze). ``clean`` means no LEAK; ``n_unproven``
says how much of the replay rests on trust.
"""

from __future__ import annotations

import sqlite3
from pathlib import Path
from typing import Any

from . import branches, controls, origins, policies, sources, store
from .contracts import Evidence, Question, RunRecord

DERIVED_KINDS = ("entity", "claim", "event", "series", "timeline", "observation")


def _t(text: str) -> Any:
    return store.parse_time(text)


def _item(e: Evidence | dict[str, Any], cutoff: str, *, in_snapshot: bool, row: dict[str, Any] | None = None) -> dict[str, Any]:
    d = e if isinstance(e, dict) else e.model_dump()
    c, pub, acq, ev = _t(cutoff), _t(d.get("publish_time", "")), _t(d.get("acquired_at", "")), _t(d.get("event_time", ""))
    out: dict[str, Any] = {"id": d["id"], "kind": d.get("kind", ""), "event_time": d.get("event_time", ""), "publish_time": d.get("publish_time", ""),
                           "acquired_at": d.get("acquired_at", ""), "in_snapshot": in_snapshot, "verdict": "ok", "why": []}
    if pub is None or c is None:
        out["verdict"], out["why"] = "unproven", ["publish time unknown"]
    elif pub > c:
        out["verdict"], out["why"] = "LEAK", ["published after the cutoff"]
    elif acq is not None and acq > c:
        out["verdict"], out["why"] = "LEAK", ["acquired after the cutoff"]
    elif acq is None:
        out["verdict"], out["why"] = "unproven", ["acquisition time unknown: only the publish time says it predates the cutoff"]
    if ev is not None and c is not None and ev > c:
        out["why"].append("event time is after the cutoff although publish time is not")
        out["verdict"] = "LEAK"
    if not in_snapshot:
        kind = str(d.get("kind", ""))
        if kind == "entity":
            out["why"].append("entity profile: its time is the cutoff by construction (rebuilt from bounded queries); counts and latest status are not individually dated")
        elif kind in DERIVED_KINDS:
            out["why"].append(f"derived {kind} row: the index keeps no derivation time for it")
        if out["verdict"] == "ok":
            out["verdict"] = "unproven"
        if row:
            out.update(row)
    return out


def _row_provenance(db: Path | None, rid: str, cutoff: str, ledger: dict[Any, dict[str, Any]]) -> dict[str, Any]:
    """For a claim or event row: its source document and whether the acquisition ledger shows the unit holding it reached us by the cutoff."""
    if db is None:
        return {}
    from algent_backend.acquisition import store as acq

    con = sqlite3.connect(f"file:{db.as_posix()}?mode=ro", uri=True)
    try:
        for table in ("claims", "events"):
            for key in (rid, rid.split(":", 1)[-1]):
                try:
                    r = con.execute(f"SELECT t.document_id, t.origin, s.fingerprint FROM {table} t LEFT JOIN ingest_state s ON s.unit = t.origin WHERE t.id = ?", (key,)).fetchone()
                except sqlite3.OperationalError:
                    r = None
                if r:
                    got = acq.acquired_at(ledger.get((r[1], r[2])))
                    out: dict[str, Any] = {"source_document": r[0], "unit": r[1], "unit_acquired_at": got}
                    if got and _t(got) is not None and _t(got) > _t(cutoff):
                        out["leak_note"] = "the unit holding this row reached us after the cutoff"
                    return out
    finally:
        con.close()
    return {}


def _memory(run: RunRecord, q: Question, man: dict[str, Any], visible: set[str]) -> list[dict[str, Any]]:
    seen = set(man.get("memory_seen") or [])
    out = []
    for ob in branches.read_memory(run.branch_id, caller=run.branch_id):
        if ob.id not in seen:
            continue
        a, d, c = _t(ob.as_of), _t(ob.derived_at), _t(q.cutoff)
        why, verdict = [], "ok"
        if a is None or c is None or a > c:
            verdict, why = "LEAK", ["its as-of is after the cutoff"]
        missing = [s for s in ob.source_ids if s not in visible and s != q.id]
        if missing:
            verdict, why = ("unproven" if verdict == "ok" else verdict), [*why, f"sources not in the cutoff snapshot: {missing[:3]}"]
        out.append({"id": ob.id, "method": f"{ob.method}@{ob.method_version}", "as_of": ob.as_of, "derived_at": ob.derived_at, "derived_after_cutoff": bool(d and c and d > c),
                    "source_ids": ob.source_ids, "verdict": verdict, "why": why or ["private to the branch; information time (as-of) is within the cutoff"]})
    return out


def _question_text(q: Question) -> list[dict[str, Any]]:
    """The question's own text against the market as it stood at the cutoff. Rules text revised after the cutoff (a resolution note, a corrected end date) would leak."""
    if not q.source.startswith("market:"):
        return []
    try:
        m, rev = sources.market_as_of(q.source.split(":", 1)[1], q.cutoff)
    except KeyError:
        return [{"item": "question text", "verdict": "unproven", "why": ["the market is no longer in the markets store"]}]
    stored = (q.text, q.rules, q.closes_at)
    asof = (m.question, m.description, m.end_date)
    if stored != asof:
        return [{"item": "question text", "verdict": "LEAK", "why": ["the stored question differs from the market revision known at the cutoff (rules, end date or title edited later)"], "rev": rev}]
    if not rev["proven_pre_cutoff"]:
        return [{"item": "question text", "verdict": "unproven", "why": ["no stored revision of this market predates the cutoff: the rules text is the earliest we hold, first stored after it"], "rev": rev}]
    return [{"item": "question text", "verdict": "ok", "why": [f"market revision stored at {rev['rev_updated_at']}"], "rev": rev}]


def _price(q: Question, prompt: str) -> dict[str, Any]:
    from algent_backend.markets import store as ms

    mp, at = q.reference.get("market_p"), q.reference.get("market_p_at", "")
    why, verdict = [], "ok"
    if mp is None:
        return {"item": "market reference price", "verdict": "ok", "why": ["no reference price on the question"], "p": None}
    if not at or _t(at) is None or _t(at) > _t(q.cutoff):
        verdict, why = "LEAK", ["the reference price is not dated at or before the cutoff"]
    snap = ms.price_at(sorted(ms.snapshots(q.source.split(":", 1)[-1]), key=lambda s: s.at), q.cutoff) if q.source.startswith("market:") else None
    if snap is not None and abs(snap.p - mp) > 1e-9:
        verdict, why = "LEAK", [*why, f"the stored price {mp} differs from the price on file at the cutoff {snap.p}"]
    shown = f"{round(mp * 100)}%"
    if shown in prompt:
        verdict, why = ("unproven" if verdict == "ok" else verdict), [*why, f"{shown} appears in the prompt: check it is not the market price"]
    return {"item": "market reference price", "p": mp, "price_at": at, "cutoff": q.cutoff, "verdict": verdict, "why": why or ["dated at or before the cutoff; absent from the blind prompt"]}


def audit_run(rid: str, *, db: Path | str | None = None) -> dict[str, Any]:
    raw = store.read_json(f"runs/{rid}/run.json")
    if raw is None:
        raise KeyError(f"no run {rid}")
    run = RunRecord.model_validate(raw)
    q = Question.model_validate(store.read_json(f"questions/{run.question_id}.json"))
    man = store.read_json(f"runs/{rid}/manifest.json") or {}
    snap = store.read_json(f"snapshots/{run.snapshot}.json") or {"items": [], "meta": {}}
    items = {e["id"]: Evidence.model_validate(e) for e in snap["items"]}
    prompt = store.path(f"runs/{rid}/prompt.txt").read_text(encoding="utf-8") if store.exists(f"runs/{rid}/prompt.txt") else ""
    dbp = Path(db) if db else None
    ledger: dict[Any, dict[str, Any]] = {}
    if dbp is not None:
        from algent_backend.acquisition import store as acq

        ledger = acq.load()

    evidence = []
    for s in man.get("shown", []):
        e = items.get(s["id"])
        if e is not None:
            it = _item(e, q.cutoff, in_snapshot=True)
            if s.get("content_hash") and s["content_hash"] != (e.content_hash or store.digest(e.body)):
                it["verdict"], it["why"] = "LEAK", [*it["why"], "the body shown differs from the snapshot body"]
        else:
            it = _item(s | {"kind": s["id"].split(":", 1)[0] if ":" in s["id"] else ""}, q.cutoff, in_snapshot=False,
                       row=_row_provenance(dbp, s["id"], q.cutoff, ledger) if s["id"].split(":", 1)[0] in ("claim", "event") else None)
            if it.get("leak_note"):
                it["verdict"], it["why"] = "LEAK", [*it["why"], it["leak_note"]]
        evidence.append(it)

    again = {e.id: e.origin_chain for e in origins.annotate(sorted(items.values(), key=lambda e: e.id))}
    mismatched = sorted(i for i, e in items.items() if again.get(i) != e.origin_chain)
    late = sorted(i for i, e in items.items() if any(o not in items for o in e.origin_chain))
    features = [{"item": f"origin chains ({origins.METHOD})", "derived_at": "at snapshot time (after the cutoff), from documents visible at the cutoff only",
                 "verdict": "LEAK" if mismatched or late else "ok",
                 "why": [f"recomputed over the {len(items)} visible documents; {len(mismatched)} differ from the stored annotation", f"{len(late)} chain origins are not in the snapshot"]
                 if mismatched or late else [f"recomputed over the {len(items)} visible documents: identical to the stored annotation, every chain origin is visible"]}]
    research = man.get("research") or {}
    if research:
        features.append({"item": "planned research over the cutoff-bounded corpus", "hidden_by_cutoff": research.get("hidden_by_cutoff", {}),
                         "unproven_derived_rows": research.get("unproven_derived_rows", "not recorded (run predates the ledger check)"), "knob_drift": research.get("knob_drift", {}),
                         "verdict": "unproven" if research.get("unproven_derived_rows") or "unproven_derived_rows" not in research else "ok",
                         "why": ["claim and event rows with no source document are kept on their own date unless the acquisition ledger shows a later acquisition"]})
    memory = _memory(run, q, man, set(items))
    context = [*_question_text(q), _price(q, prompt)]
    drift = controls.impl_drift(policies.load_protocol(run.protocol_id))
    if drift:
        context.append({"item": "code under the run", "verdict": "unproven", "why": ["the evidence policy's code changed since this protocol was frozen: this run may predate a fix"], "drift": drift})
    every = [*evidence, *features, *memory, *context]
    leaks = [x for x in every if x["verdict"] == "LEAK"]
    unproven = [x for x in every if x["verdict"] == "unproven"]
    return {"run": rid, "question": q.id, "protocol": run.protocol_id, "cutoff": q.cutoff, "clean": not leaks, "n_leaks": len(leaks), "n_unproven": len(unproven),
            "evidence": evidence, "features": features, "memory": memory, "context": context,
            "summary": [f"{x.get('id') or x.get('item')}: {'; '.join(x['why'])}" for x in leaks] or ["no stored time contradicts the cutoff"]}


def audit_question(question_id: str, *, db: Path | str | None = None) -> list[dict[str, Any]]:
    from . import score

    return [audit_run(r.run_id, db=db) for r in score.runs() if r.question_id == question_id]


def pick_question(set_doc: dict[str, Any]) -> str:
    """A question from a set with at least one run: the first (the set is ordered round-robin by topic, so this is a fixed, unbiased choice)."""
    from . import score

    have = {r.question_id for r in score.runs()}
    for e in set_doc["questions"]:
        if e["id"] in have:
            return e["id"]
    raise KeyError("no question of this set has a run yet")

