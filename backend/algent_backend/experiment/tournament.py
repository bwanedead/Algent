"""
Tournament: successive halving over a common question set, to find the best recipe among many candidates without paying for every candidate on every question.

Round one: every candidate answers the first ``first`` questions of the set (a fixed, topic-mixed order: questions sorted by the digest of their id). The candidates are
ranked by PAIRED Brier-vs-market on the questions all of them answered (per question: the candidate's Brier minus the market's Brier at the cutoff; mean with a standard
error), the top half is kept, the slice doubles, and the survivors answer the new questions only (a run already stored is reused for free). It ends when one candidate
remains. Once the slice is the whole set the ranking cannot change, so the remaining halvings cost nothing; the result then says plainly whether the winner is separated
from the runner-up (lead beyond two standard errors) or merely first.

A candidate is a spec (``genome.parse``): a named mind or a stored protocol, with at most ONE changed policy. A candidate carrying a calibration policy runs its RAW
protocol's runs (no duplicate paid call) and is ranked on the recalibrated probabilities, each map fitted only on forecasts resolved before that question's cutoff.
An abstention scores as a 50% forecast. Means closer than ``flags.TOURNAMENT_TIE_EPS`` are a tie, which goes to the cheaper candidate.

SPEND. ``budget_usd`` (``flags.TOURNAMENT_USD``) is checked BEFORE every model call against that call's maximum cost; the first call that would exceed it stops the
tournament, which reports what it had (and declares no winner). Nothing is called without ``live``. The result is stored write-once under ``tournaments/<id>.json``
with the candidates' genealogy (parent and changed policy); the id is the digest of the content, so the same outcome stored twice is one file.
"""

from __future__ import annotations

import math
from typing import Any

from . import branches, calibrate, calibration, flags, genome, policies, qset, runner, score, store
from .contracts import Protocol, Question, RunRecord


def order(doc: dict[str, Any]) -> list[Question]:
    """The set's questions in the tournament's fixed order (by digest of the id: stable, and it mixes topics instead of following the build's round-robin tail)."""
    return sorted(qset.questions_of(doc), key=lambda q: store.digest(q.id))


def slice_sizes(n_questions: int, first: int) -> list[int]:
    sizes, s = [], max(1, first)
    while s < n_questions:
        sizes.append(s)
        s *= 2
    return sizes + [n_questions]


def survivors(n: int) -> int:
    return max(1, math.ceil(n / 2))


class Candidate:
    def __init__(self, spec: str):
        self.spec = spec
        self.proto: Protocol = genome.parse(spec)
        self.raw, self.cal = calibration.split(self.proto)           # the protocol that runs, and the calibration applied to its stored runs
        self.branch = branches.ensure(self.raw.name, self.raw)
        self.usd = 0.0
        self.runs = 0


class Arena:
    """The candidates, the set's questions in tournament order, and each question's one shared snapshot."""

    def __init__(self, doc: dict[str, Any], specs: list[str], source: Any):
        self.cands: list[Candidate] = []
        for s in specs:
            c = Candidate(s)
            if all(c.proto.id != o.proto.id for o in self.cands):
                self.cands.append(c)
        self.qs = order(doc)
        self.snaps = {q.id: runner.build_snapshot(source, q)[0] for q in self.qs}

    def rid(self, c: Candidate, q: Question) -> str:
        return runner.run_id_for(q, c.raw.id, self.snaps[q.id])

    def record(self, c: Candidate, q: Question) -> RunRecord | None:
        raw = store.read_json(f"runs/{self.rid(c, q)}/run.json")
        return RunRecord.model_validate(raw) if raw else None

    def tally(self, qs: list[Question]) -> None:
        """Cost and run count of each candidate on these questions, from the stored runs (so reused ones count too)."""
        for c in self.cands:
            recs = [r for q in qs if (r := self.record(c, q))]
            c.usd, c.runs = sum(r.usd for r in recs), len(recs)

    def fitters(self, live: list[dict[str, Any]]) -> dict[str, calibration.Fitter]:
        lab = calibrate.lab_rows()
        return {c.raw.id: calibration.Fitter(lab=calibrate.observations([r for r in lab if r["protocol"] == c.raw.id]), live=calibrate.observations(live)) for c in self.cands}

    def diffs(self, c: Candidate, qs: list[Question], res: dict[str, Any], fitters: dict[str, calibration.Fitter]) -> dict[str, float]:
        """Per question: the candidate's Brier minus the market's Brier at the cutoff (an abstention is a 50% forecast; a calibration policy maps the stored p)."""
        out = {}
        for q in qs:
            mp, r, rec = q.reference.get("market_p"), res.get(q.id), self.record(c, q)
            if mp is None or r is None or rec is None:
                continue
            p = 0.5 if rec.p is None else rec.p if c.cal is None else fitters[c.raw.id].apply(c.cal, rec.p, q.cutoff)[0]
            o = 1 if r.outcome == "yes" else 0
            out[q.id] = score.brier(p, o) - score.brier(mp, o)
        return out

    def rank(self, alive: list[Candidate], qs: list[Question], res: dict[str, Any], fitters: dict[str, calibration.Fitter]) -> list[dict[str, Any]]:
        """Paired Brier-vs-market on the questions EVERY listed candidate answered, best first; means within the tie width go to the cheaper candidate."""
        per = {c.spec: self.diffs(c, qs, res, fitters) for c in alive}
        shared = sorted(set.intersection(*(set(d) for d in per.values()))) if per else []
        rows = []
        for c in alive:
            m, se = score.mean_se([per[c.spec][k] for k in shared])
            rows.append({"spec": c.spec, "name": c.proto.name, "protocol": c.proto.id, "n": len(shared), "brier_minus_market": m, "se": se, "usd": round(c.usd, 4),
                         "usd_per_run": round(c.usd / c.runs, 4) if c.runs else 0.0})
        eps = flags.TOURNAMENT_TIE_EPS
        rows.sort(key=lambda r: (999.0 if r["brier_minus_market"] is None else round(r["brier_minus_market"] / eps), r["usd_per_run"]))
        for i, r in enumerate(rows):
            r["rank"] = i + 1
        if len(rows) > 1 and len(shared) >= 2:                                # the leader's paired lead over the next one, with its standard error
            a, b = per[rows[0]["spec"]], per[rows[1]["spec"]]
            rows[0]["lead_over_next"], rows[0]["lead_se"] = score.mean_se([b[k] - a[k] for k in shared])
        return rows


def plan(doc: dict[str, Any], specs: list[str], source: Any, *, budget_usd: float = flags.TOURNAMENT_USD, first: int = flags.TOURNAMENT_FIRST_SLICE) -> dict[str, Any]:
    """What a live tournament would do and the most it could spend (a bound: later rounds assume the costliest candidate survives). Calls no model."""
    ar = Arena(doc, specs, source)
    alive, prev, rounds, total = len(ar.cands), 0, [], 0.0
    worst = max((qset.max_cost(c.raw) for c in ar.cands), default=0.0)
    for i, size in enumerate(slice_sizes(len(ar.qs), first)):
        new = ar.qs[prev:size]
        if i == 0:
            todo = [c for c in ar.cands for q in new if ar.record(c, q) is None]
            cost, n_todo = sum(qset.max_cost(c.raw) for c in todo), len(todo)
        else:
            n_todo = alive * len(new)
            cost = n_todo * worst
        rounds.append({"round": i + 1, "slice": size, "candidates": alive, "new_runs_at_most": n_todo, "max_usd": round(cost, 4)})
        total += cost
        prev, alive = size, survivors(alive)
        if alive <= 1:
            break
    return {"set": doc["id"], "candidates": [genome.describe(c.proto) | {"spec": c.spec, "calibration": c.cal.ref if c.cal else "", "runs_on": c.raw.name} for c in ar.cands],
            "n_questions": len(ar.qs), "rounds": rounds, "estimated_max_usd": round(total, 4), "budget_usd": budget_usd, "within_budget": total <= budget_usd,
            "note": "an upper bound: stored runs are reused free, and the tournament stops at the first call that would exceed the budget"}


def run(doc: dict[str, Any], specs: list[str], source: Any, ask_for: Any, *, live: bool, budget_usd: float = flags.TOURNAMENT_USD, first: int = flags.TOURNAMENT_FIRST_SLICE,
        plan_ask_for: Any = None, corpus: Any = None, live_rows: list[dict[str, Any]] | None = None) -> dict[str, Any]:
    """Successive halving. Without ``live`` nothing is called and the plan is returned. ``live_rows`` are the live bots' resolved forecasts for a ``platt-live`` candidate."""
    if not live:
        return {"live": False, **plan(doc, specs, source, budget_usd=budget_usd, first=first), "refused": "add --live to spend; nothing was called"}
    ar = Arena(doc, specs, source)
    res = {q.id: r for q in ar.qs if (r := score.resolve(q)) is not None and r.outcome in ("yes", "no")}
    liv = live_rows if live_rows is not None else (calibrate.live_rows() if any(c.cal and "live" in c.cal.params.get("sources", []) for c in ar.cands) else [])
    spent, stopped, alive, prev, rounds = 0.0, "", list(ar.cands), 0, []
    for i, size in enumerate(slice_sizes(len(ar.qs), first)):
        for c in alive:
            for q in ar.qs[prev:size]:
                if ar.record(c, q) is not None:
                    continue
                cost = qset.max_cost(c.raw)
                if spent + cost > budget_usd:
                    stopped = f"the ${budget_usd:.2f} budget would be exceeded by the next call (spent ${spent:.3f}, next up to ${cost:.3f})"
                    break
                pa = plan_ask_for(c.raw.policies["evidence"]) if plan_ask_for and policies.is_planned(c.raw.policies["evidence"]) else None
                spent += runner.run_branch(q, c.branch, ar.snaps[q.id], ask_for(c.raw), live=True, plan_ask=pa, corpus=corpus).usd
            if stopped:
                break
        ar.tally(ar.qs[:size])
        table = ar.rank(alive, ar.qs[:size], res, ar.fitters(liv))
        keep = [r["spec"] for r in table] if stopped else [r["spec"] for r in table[: survivors(len(table))]]
        rounds.append({"round": i + 1, "slice": size, "alive": table, "kept": keep, "eliminated": [r["spec"] for r in table if r["spec"] not in keep]})
        alive, prev = [c for c in alive if c.spec in keep], size
        if stopped or len(alive) <= 1:
            break
    while len(alive) > 1 and not stopped:                                     # the slice is the whole set: further halving is the same ranking, free
        table = ar.rank(alive, ar.qs, res, ar.fitters(liv))
        keep = [r["spec"] for r in table[: survivors(len(table))]]
        rounds.append({"round": len(rounds) + 1, "slice": len(ar.qs), "alive": table, "kept": keep, "eliminated": [r["spec"] for r in table if r["spec"] not in keep],
                       "note": "whole set already answered: this halving costs nothing"})
        alive = [c for c in alive if c.spec in keep]
    final = rounds[-1]["alive"][0] if rounds and rounds[-1]["alive"] else None
    lead = final.get("lead_over_next") if final else None
    result = {"set": doc["id"], "params": {"budget_usd": budget_usd, "first_slice": first, "specs": specs},
              "candidates": [genome.describe(c.proto) | {"spec": c.spec, "calibration": c.cal.ref if c.cal else ""} for c in ar.cands], "rounds": rounds,
              "winner": (final or {}).get("spec") if not stopped else None, "leader": (final or {}).get("spec"),
              "separated": bool(lead is not None and final.get("lead_se") and lead > 2 * final["lead_se"]), "spent_usd": round(spent, 4), "stopped": stopped}
    tid = store.digest(result)[:10]
    if not store.exists(f"tournaments/{tid}.json"):
        store.write_once(f"tournaments/{tid}.json", {"id": tid, **result})
        store.append("tournaments/index.jsonl", {"id": tid, "set": doc["id"], "winner": result["winner"], "spent_usd": result["spent_usd"], "at": store.now_iso()})
    return {"id": tid, "live": True, **result}


def render(doc: dict[str, Any]) -> str:
    if not doc.get("live"):
        lines = [f"PLAN (nothing called) set {doc['set']}: {len(doc['candidates'])} candidates, {doc['n_questions']} questions, at most ${doc['estimated_max_usd']:.3f} of ${doc['budget_usd']:.2f}"]
        lines += [f"  round {r['round']}: first {r['slice']} questions, {r['candidates']} candidates, up to {r['new_runs_at_most']} new runs, <= ${r['max_usd']:.3f}" for r in doc["rounds"]]
        return "\n".join(lines + [doc.get("refused", "")])
    lines = [f"tournament on set {doc['set']}: spent ${doc.get('spent_usd', 0):.3f}" + (f"  STOPPED: {doc['stopped']}" if doc.get("stopped") else "")]
    for r in doc.get("rounds", []):
        lines.append(f"round {r['round']}: first {r['slice']} questions, {len(r['alive'])} candidates" + (f"  ({r['note']})" if r.get("note") else ""))
        for a in r["alive"]:
            lead = "-" if a["brier_minus_market"] is None else f"{a['brier_minus_market']:+.3f} +/- {'-' if a['se'] is None else a['se']}"
            lines.append(f"  {a['rank']}. {a['spec'][:44]:44} {lead:>18}  n={a['n']}  ${a['usd']:.3f}" + ("" if a["spec"] in r["kept"] else "  out"))
    if doc.get("winner"):
        lines.append(f"winner: {doc['winner']} ({'separated from the runner-up' if doc.get('separated') else 'first, but not separated from the runner-up by two standard errors'})")
    elif doc.get("leader"):
        lines.append(f"no winner declared; leader so far: {doc['leader']}")
    return "\n".join(lines)
