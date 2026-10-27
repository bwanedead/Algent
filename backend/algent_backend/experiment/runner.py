"""
A controlled run: ONE question, ONE evidence snapshot, several branches. Each branch's protocol picks from the snapshot with its own evidence policy and
asks its own model with its own frozen prompt. Everything that decides the result is written down BEFORE the answer is scored: the snapshot, the manifest
(exactly which evidence ids the branch could see, with times and the cutoff), the prompt as sent, the raw output, the cost, and the forecast (write-once).
An audit reads those files; it never re-derives them.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

from . import branches, policies, store
from .access import Reader
from .contracts import Branch, Evidence, Observation, Question, RunRecord
from .policies import render_task, retriever

#: (task, role) -> (structured answer with .probability / .rationale / .cited, usd). Stubbed in tests; ``live_ask`` is the house model under the budget gate.
Ask = Callable[[str, str], tuple[Any, float]]


def save_question(q: Question) -> Question:
    store.write_once(f"questions/{q.id}.json", q)
    return q


def build_snapshot(source: Any, q: Question) -> tuple[str, list[Evidence], dict[str, Any]]:
    """The shared evidence snapshot for a question: everything visible at the cutoff, stored by digest. Excluded ids are recorded with their reason
    (ids only, never bodies)."""
    reader = Reader(source.candidates(q.cutoff), [], [], cutoff=q.cutoff, branch="")
    items = sorted(reader.evidence(), key=lambda e: e.id)
    meta = {"cutoff": q.cutoff, "source": source.name, "acquired_known": source.acquired_known, "n_visible": len(items), "excluded": reader.excluded}
    sid = store.digest({"items": [e.model_dump() for e in items], "meta": meta})
    store.write_once(f"snapshots/{sid}.json", {"meta": meta, "items": [e.model_dump() for e in items]})
    return sid, items, meta


def load_snapshot(sid: str) -> tuple[list[Evidence], dict[str, Any]]:
    raw = store.read_json(f"snapshots/{sid}.json")
    return [Evidence.model_validate(e) for e in raw["items"]], raw["meta"]


def run_id_for(q: Question, protocol_id: str, snapshot: str) -> str:
    return store.digest([q.id, protocol_id, snapshot])[:12]


def run_branch(q: Question, b: Branch, snapshot: str, ask: Ask, *, live: bool = False, mode: str = "controlled", plan_ask: Any = None, corpus: Any = None) -> RunRecord:
    rid = run_id_for(q, b.protocol_id, snapshot)
    done = store.read_json(f"runs/{rid}/run.json")
    if done:                                                 # never redo paid work: the same (question, protocol, snapshot) is already on disk
        return RunRecord.model_validate(done)
    proto = policies.load_protocol(b.protocol_id)
    items, meta = load_snapshot(snapshot)
    reader = Reader(items, [], branches.read_memory(b.id, caller=b.id), cutoff=q.cutoff, branch=b.id)
    ev_pol = proto.policies["evidence"]
    plan_usd, research_trace, evidence_text = 0.0, None, None
    if policies.is_planned(ev_pol):                          # production's planned research over the cutoff-bounded corpus: its own gate is CutoffCorpus
        got = policies.rp.retrieve(reader.evidence(), q, ev_pol.params, plan_ask=plan_ask, corpus=corpus)
        chosen, evidence_text, plan_usd, research_trace = got.chosen, got.text, got.usd, got.trace
    else:
        chosen = retriever(ev_pol)(reader.evidence(), q, ev_pol.params)
        # defence in depth: whatever a policy returns must still be inside what the reader allows
        allowed = {e.id for e in reader.evidence()}
        chosen = [e for e in chosen if e.id in allowed]
    memory_seen = [m.id for m in reader.memory()]
    task = render_task(proto, q, chosen, [m.text for m in reader.memory()], evidence_text)
    role = proto.policies["prompts"].params["role"]
    started = store.now_iso()
    out, usd = ask(task, role)
    usd = float(usd or 0.0) + plan_usd
    shown = {e.id for e in chosen}
    from algent_backend.markets.forecast import as_probability

    p_raw = getattr(out, "probability", None)
    frac = as_probability(p_raw)                                                         # percent answers ("2" = 2%) are read, not dropped
    pp = proto.policies["prediction"].params
    p = round(min(pp["p_max"], max(pp["p_min"], frac)), 4) if frac is not None else None  # an unusable answer is an abstention, kept and evaluated
    cited = [c for c in (getattr(out, "cited", None) or []) if c in shown]
    rationale = " ".join(str(getattr(out, "rationale", "")).split())[:900]
    manifest = {"question": q.id, "cutoff": q.cutoff, "snapshot": snapshot, "source": meta["source"], "acquired_known": meta["acquired_known"],
                "evidence_policy": ev_pol.ref, "n_visible_in_snapshot": meta["n_visible"], "n_excluded_at_cutoff": len(meta["excluded"]),
                "time_bounds": {"earliest_publish": min((e.publish_time for e in chosen), default=""), "latest_publish": max((e.publish_time for e in chosen), default=""),
                                "cutoff": q.cutoff},
                "shown": [{"id": e.id, "content_hash": e.content_hash or store.digest(e.body), "event_time": e.event_time, "publish_time": e.publish_time,
                           "acquired_at": e.acquired_at} for e in chosen], "memory_seen": memory_seen}
    if research_trace is not None:
        manifest["research"] = research_trace
    output = {"p": p, "abstained": p is None, "raw_probability": p_raw, "rationale": rationale, "cited": cited, "usd": usd,
              "trace": {"policies": {k: v.ref for k, v in proto.policies.items()}, "policy_digests": {k: v.digest for k, v in proto.policies.items()}}}
    store.write_once(f"runs/{rid}/manifest.json", manifest)
    store.write_once(f"runs/{rid}/prompt.txt", task)
    store.write_once(f"runs/{rid}/output.json", output)
    rec = RunRecord(run_id=rid, question_id=q.id, protocol_id=proto.id, branch_id=b.id, mode=mode, snapshot=snapshot,  # type: ignore[arg-type]
                    manifest_digest=store.digest(manifest), prompt_digest=store.digest(task), output_digest=store.digest(output), p=p, usd=round(float(usd), 6),
                    live=live, started_at=started, impl_shas={k: v.impl_sha for k, v in proto.policies.items() if v.impl_sha})
    store.write_once(f"runs/{rid}/run.json", rec)
    if frac is not None and memory_writes_enabled(proto):
        branches.append_memory(b.id, Observation(id=f"{b.id}:{rid}", source_ids=cited or sorted(shown)[:1] or [q.id], method="blind-forecast",
                                                 method_version=proto.policies["prompts"].ref, text=f"{q.text} -> {p}: {rationale}", derived_at=store.now_iso(),
                                                 as_of=q.cutoff, branch=b.id), caller=b.id)
    return rec


def memory_writes_enabled(proto: Any) -> bool:
    m = proto.policies.get("memory")
    return bool(m and m.params.get("write"))


def preview(q: Question, b: Branch, snapshot: str) -> list[str]:
    """The ids a branch WOULD be shown (free: no model call)."""
    proto = policies.load_protocol(b.protocol_id)
    reader = Reader(load_snapshot(snapshot)[0], [], branches.read_memory(b.id, caller=b.id), cutoff=q.cutoff, branch=b.id)
    pol = proto.policies["evidence"]
    if policies.is_planned(pol):
        return ["(planned at run time by a model over the cutoff-bounded corpus)"]
    return [e.id for e in retriever(pol)(reader.evidence(), q, pol.params)]


def run_controlled(q: Question, bs: list[Branch], source: Any, ask_for: Callable[[Any], Ask], *, live: bool = False, plan_ask_for: Callable[[Any], Any] | None = None,
                   corpus: Any = None) -> list[RunRecord]:
    """Same snapshot and question for every branch; only the protocols differ. ``plan_ask_for``/``corpus`` serve protocols whose evidence policy plans research."""
    save_question(q)
    sid, _, _ = build_snapshot(source, q)
    out = []
    for b in bs:
        proto = policies.load_protocol(b.protocol_id)
        pa = plan_ask_for(proto.policies["evidence"]) if plan_ask_for and policies.is_planned(proto.policies["evidence"]) else None
        out.append(run_branch(q, b, sid, ask_for(proto), live=live, plan_ask=pa, corpus=corpus))
    return out


def live_ask(proto: Any) -> Ask:
    """The house model under the budget gate, built from the protocol's FROZEN model and prompt policies and capped for the lab."""
    from algent_backend.markets import forecast as fc

    from . import flags

    m = proto.policies["model"].params
    return fc.default_ask(proto.policies["prompts"].params["role"], cap_usd=min(float(m["cap_usd"]), flags.RUN_CAP_USD), effort=m["effort"], max_tokens=int(m["max_tokens"]))


def verify(rid: str) -> list[str]:
    """Problems found re-hashing the stored files of a run against its record (empty = intact). Reads only what was stored."""
    raw = store.read_json(f"runs/{rid}/run.json")
    if raw is None:
        return [f"no run {rid}"]
    rec = RunRecord.model_validate(raw)
    bad = []
    for fname, want in (("manifest.json", rec.manifest_digest), ("output.json", rec.output_digest)):
        data = store.read_json(f"runs/{rid}/{fname}")
        if data is None or store.digest(data) != want:
            bad.append(f"{fname} does not match the run record")
    prompt = store.path(f"runs/{rid}/prompt.txt")
    if not prompt.exists() or store.digest(prompt.read_text(encoding="utf-8")) != rec.prompt_digest:
        bad.append("prompt.txt does not match the run record")
    if store.read_json(f"snapshots/{rec.snapshot}.json") is None:
        bad.append("snapshot missing")
    for pv in policies.load_protocol(rec.protocol_id).policies.values():
        if store.read_json(f"policies/{pv.digest}.json") is None:
            bad.append(f"policy {pv.ref} missing")
    return bad
