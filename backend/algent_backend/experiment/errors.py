"""
Per-question error breakdown (``newsroom lab errors --set latest``): for every resolved question of a set and every protocol that answered it, the forecast, the
outcome, the Brier score, the market at the cutoff, how much evidence the mind saw and from how many independent chains, whether research found anything the mind
actually used, and a one-line tag naming the likeliest cause. The tags are deterministic reads of stored facts, never a model's opinion, and they are hints for a
human: a row that fits no rule is left blank.

  extreme/overconfident   on the wrong side of 50% by at least ``flags.ERR_EXTREME_DIST``
  retrieval miss          wrong, nothing relevant used, yet the cutoff snapshot holds documents that overlap the question's words
  out-of-coverage         wrong, nothing relevant used, and the snapshot holds nothing that overlaps the question
  wrong base rate         (prior minds) the stated base rate was on the wrong side and the final answer stayed near it
  possible leak           on the right side with Brier <= ``flags.ERR_LEAK_BRIER`` while using no relevant evidence, or the replay audit found a LEAK
  invalid output          no usable probability (a recorded failure)
"""

from __future__ import annotations

from typing import Any

from . import audit, flags, genealogy, policies, qset, runner, score, store
from .contracts import Question, RunRecord


def _relevant(out: dict[str, Any], n_shown: int) -> bool:
    """Research found something the mind used: evidence was shown, it cited some of it, and it did not call the evidence a gap."""
    return n_shown > 0 and bool(out.get("cited")) and out.get("evidence_verdict") != "gap"


def tag_for(*, p: float | None, outcome: int, relevant: bool, snapshot_overlap: bool, structured: dict[str, Any] | None, audit_leaks: int) -> str:
    if p is None:
        return "invalid output"
    tags = []
    wrong = (p > 0.5) != bool(outcome) and p != 0.5
    if wrong and abs(p - 0.5) >= flags.ERR_EXTREME_DIST:
        tags.append("extreme/overconfident")
    if wrong and not relevant:
        tags.append("retrieval miss" if snapshot_overlap else "out-of-coverage")
    base = (structured or {}).get("base_rate_pct")
    if wrong and isinstance(base, (int, float)) and (base / 100 > 0.5) != bool(outcome) and abs(p - base / 100) < 0.1:
        tags.append("wrong base rate")
    if audit_leaks or (not wrong and score.brier(p, outcome) <= flags.ERR_LEAK_BRIER and not relevant):
        tags.append("possible leak")
    return "; ".join(tags)


def _row(r: RunRecord, q: Question, outcome: int) -> dict[str, Any]:
    out = store.read_json(f"runs/{r.run_id}/output.json") or {}
    man = store.read_json(f"runs/{r.run_id}/manifest.json") or {}
    chains = man.get("chains") or {}
    n_shown = int(chains.get("n_shown") or len(man.get("shown", [])))
    items, _ = runner.load_snapshot(r.snapshot)
    overlap = bool(policies.keyword_overlap(items, q, {"k": 1}))
    leaks = audit.audit_run(r.run_id)["n_leaks"]
    relevant = _relevant(out, n_shown)
    return {"question": q.id, "text": q.text[:70], "protocol": r.protocol_id, "run": r.run_id, "p": r.p, "outcome": "yes" if outcome else "no",
            "brier": None if r.p is None else round(score.brier(r.p, outcome), 4), "market_p": q.reference.get("market_p"), "n_evidence": n_shown,
            "n_independent": chains.get("n_independent"), "found_relevant": relevant,
            "tag": tag_for(p=r.p, outcome=outcome, relevant=relevant, snapshot_overlap=overlap, structured=out.get("structured"), audit_leaks=leaks)}


def breakdown(doc: dict[str, Any], *, resolve_now: bool = True) -> dict[str, Any]:
    names = {pid: p.name for pid, p in genealogy.all_protocols().items()}
    runs = [r for r in score.runs() if r.mode == "controlled"]
    rows, unresolved = [], []
    for q in qset.questions_of(doc):
        res = score.resolve(q) if resolve_now else score._stored(q.id)
        if res is None or res.outcome == "void":
            unresolved.append(q.id)
            continue
        rows += [{**_row(r, q, 1 if res.outcome == "yes" else 0), "name": names.get(r.protocol_id, r.protocol_id)} for r in runs if r.question_id == q.id]
    return {"set": doc["id"], "rows": sorted(rows, key=lambda x: (x["question"], x["name"])), "unresolved": unresolved}


def render(report: dict[str, Any]) -> str:
    head = f"{'question':34} {'protocol':26} {'p':>5} {'out':>3} {'brier':>6} {'mkt':>5} {'ev':>3} {'ind':>3} {'rel':>3}  tag"
    lines = [head, "-" * len(head)]
    for r in report["rows"]:
        f = lambda v: "-" if v is None else f"{v:.2f}"  # noqa: E731
        lines.append(f"{r['question'][:34]:34} {r['name'][:26]:26} {f(r['p']):>5} {r['outcome']:>3} {f(r['brier']):>6} {f(r['market_p']):>5} {r['n_evidence']:>3} "
                     f"{'-' if r['n_independent'] is None else r['n_independent']:>3} {'y' if r['found_relevant'] else 'n':>3}  {r['tag']}")
    if report["unresolved"]:
        lines.append(f"unresolved (not scored): {len(report['unresolved'])}")
    return "\n".join(lines)
