"""
``newsroom lab`` — the experiment framework, phases 1 and 2 (docs/architecture/experiment-framework.md). Manual and isolated: it reads the markets store and the
corpus index, writes only to its own store (ALGENT_EXPERIMENT_STORE), and calls a model only with ``run --live`` (capped, under the budget gate).

    newsroom lab questions [--limit N]                      resolved markets in the markets store that a historical question can be built from (free)
    newsroom lab run --market ID --cutoff ISO [--corpus DIR] [--k N] [--live]
                                                            P0 (frozen blind forecaster) vs P1 (P0 with the evidence-retrieval policy changed), one snapshot.
                                                            Without --live: freezes P0, builds the snapshot and prints what each branch WOULD see; no model call
    newsroom lab questions --set build [--min N] [--hours H]   assemble the mandatory common question set from resolved markets (free); --set list | ID shows sets
    newsroom lab run --set ID|latest [--protocols p0,p0b] [--cap USD] [--corpus DIR] [--live]
                                                            every named protocol on the whole set, controlled; total spend capped (experiment/flags.SET_RUN_CAP_USD);
                                                            without --live: builds snapshots and prints what would run and its maximum cost. Re-running continues
    newsroom lab decide --set ID|latest --forecast p0b [--cap USD] [--live]   the frozen trader on a forecast protocol's stored forecasts (decision replay)
    newsroom lab list                                       questions, branches, runs
    newsroom lab show ID                                    a run (manifest, prompt, output, integrity) or a question
    newsroom lab branch --from BRANCH --name NAME [--evidence NAME@V]   fork a branch with ONE evidence policy changed; the original is untouched
    newsroom lab score                                      resolve what has settled and print the scoreboards (per mode)
    newsroom lab verify RUN_ID                              re-hash the stored files of a run against its record

Every command prints one JSON document.
"""

from __future__ import annotations

import json
from typing import Any


def add_parser(sub: Any) -> None:
    p = sub.add_parser("lab", help="experiment framework (manual, isolated): compare protocol versions on one question and one evidence snapshot")
    verbs = p.add_subparsers(dest="lab_cmd", required=True)
    q = verbs.add_parser("questions", help="resolved markets a question can be built from")
    q.add_argument("--limit", type=int, default=20)
    q.add_argument("--set", dest="qset", help="build | list | ID: the common question set")
    q.add_argument("--min", dest="min_n", type=int, help="build: aim for at least this many questions")
    q.add_argument("--hours", type=float, help="build: cutoff this many hours before resolution")
    q.set_defaults(handler=run_questions)
    r = verbs.add_parser("run", help="P0 vs P1 on one question")
    r.add_argument("--market", help="a single resolved market (with --cutoff), or use --set")
    r.add_argument("--cutoff", help="ISO instant: the information cutoff (before the market resolved)")
    r.add_argument("--set", dest="qset", help="run every named protocol on this common question set (ID or latest)")
    r.add_argument("--protocols", default="p0,p0b", help="with --set: comma-separated names (p0, p0b) or protocol ids")
    r.add_argument("--cap", type=float, help="with --set: total spend cap for this invocation in USD")
    r.add_argument("--corpus", help="corpus store directory (default: ALGENT_CORPUS_STORE / corpus_store)")
    r.add_argument("--k", type=int, help="documents each protocol may show the model")
    r.add_argument("--live", action="store_true", help="really call the model (cap per call: experiment/flags.RUN_CAP_USD)")
    r.set_defaults(handler=run_run)
    verbs.add_parser("list", help="questions, branches, runs").set_defaults(handler=run_list)
    s = verbs.add_parser("show", help="a run or a question")
    s.add_argument("id")
    s.set_defaults(handler=run_show)
    b = verbs.add_parser("branch", help="fork a branch with one evidence policy changed")
    b.add_argument("--from", dest="parent", required=True)
    b.add_argument("--name", required=True)
    b.add_argument("--evidence", required=True, help="NAME@VERSION, e.g. keyword-overlap@1")
    b.set_defaults(handler=run_branch)
    d = verbs.add_parser("decide", help="the frozen trader on a forecast protocol's stored forecasts")
    d.add_argument("--set", dest="qset", default="latest")
    d.add_argument("--forecast", default="p0b", help="the forecast protocol whose forecasts and evidence the trader is chained to")
    d.add_argument("--cap", type=float)
    d.add_argument("--live", action="store_true")
    d.set_defaults(handler=run_decide)
    sc = verbs.add_parser("score", help="scoreboards per mode, and the decision board")
    sc.add_argument("--set", dest="qset", help="restrict to a common question set (ID or latest)")
    sc.set_defaults(handler=run_score)
    v = verbs.add_parser("verify", help="integrity of a stored run")
    v.add_argument("run_id")
    v.set_defaults(handler=run_verify)


def _emit(doc: Any) -> int:
    print(json.dumps(doc, indent=2, ensure_ascii=False, default=str))
    return 0


def run_questions(args: Any) -> int:
    from algent_backend.markets import store as ms

    if args.qset:
        from algent_backend.experiment import qset, store

        if args.qset == "build":
            kw = {k: v for k, v in (("min_n", args.min_n), ("hours_before", args.hours)) if v}
            doc = qset.build(**kw)
            return _emit({"set": doc["id"], "n": len(doc["questions"]), "topics": doc["topics"], "skipped": doc["skipped"], "short_of_target": doc["short_of_target"],
                          "params": doc["params"], "store": str(store.root())})
        if args.qset == "list":
            return _emit(store.read_lines("sets/index.jsonl"))
        return _emit(qset.load(args.qset))

    rows = [m for m in ms.markets().values() if m.status == "resolved" and m.outcome in ("yes", "no")]
    rows.sort(key=lambda m: m.resolved_at, reverse=True)
    return _emit([{"market": m.id, "question": m.question, "outcome": m.outcome, "resolved_at": m.resolved_at, "n_prices": len(ms.snapshots(m.id))} for m in rows[: args.limit]])


def _set_run(args: Any) -> int:
    from algent_backend.corpus import paths
    from algent_backend.corpus.query import Corpus
    from algent_backend.experiment import flags, qset, research_policy, runner, sources

    doc = qset.load(args.qset)
    names = [n.strip() for n in args.protocols.split(",") if n.strip()]
    src = sources.CorpusSource(paths.db_file(args.corpus))
    corpus = Corpus.open(args.corpus) if args.live and "p0b" in names else None
    try:
        out = qset.run(doc, names, src, runner.live_ask, live=args.live, cap_usd=args.cap if args.cap is not None else flags.SET_RUN_CAP_USD,
                       plan_ask_for=lambda pv: research_policy.live_plan_ask(pv.params), corpus=corpus)
    finally:
        if corpus is not None:
            corpus.close()
    return _emit(out)


def run_decide(args: Any) -> int:
    from algent_backend.experiment import decision, flags, qset

    doc = qset.load(args.qset)
    return _emit(decision.replay_set(doc, qset.protocol_named(args.forecast), live=args.live, cap_usd=args.cap if args.cap is not None else flags.SET_RUN_CAP_USD))


def run_run(args: Any) -> int:
    if args.qset:
        return _set_run(args)
    if not (args.market and args.cutoff):
        print("lab run needs --market and --cutoff, or --set")
        return 2
    from algent_backend.corpus import paths
    from algent_backend.experiment import branches, flags, policies, runner, sources, store

    src = sources.CorpusSource(paths.db_file(args.corpus))
    q = sources.question_from_market(args.market, args.cutoff)
    p0 = policies.freeze_blind_forecaster()
    k = args.k or flags.EVIDENCE_K
    p1 = policies.replace_policy(p0, policies.evidence_policy("keyword-overlap", k=k), "p1-keyword-retrieval")
    b0, b1 = branches.ensure("p0", p0), branches.ensure("p1", p1)
    if not args.live:
        runner.save_question(q)
        sid, items, meta = runner.build_snapshot(src, q)
        return _emit({"live": False, "store": str(store.root()), "question": q.id, "cutoff": q.cutoff, "snapshot": sid, "visible": len(items), "excluded": len(meta["excluded"]),
                      "acquired_known": meta["acquired_known"], "would_show": {b.name: runner.preview(q, b, sid) for b in (b0, b1)},
                      "note": "add --live to call the model (<= RUN_CAP_USD per call)"})
    recs = runner.run_controlled(q, [b0, b1], src, runner.live_ask, live=True)
    return _emit([{"run": r.run_id, "branch": r.branch_id, "p": r.p, "usd": r.usd} for r in recs])


def run_list(args: Any) -> int:
    from algent_backend.experiment import score, store

    return _emit({"store": str(store.root()), "questions": sorted(score.questions()), "branches": store.listing("branches"),
                  "runs": [{"run": r.run_id, "question": r.question_id, "branch": r.branch_id, "p": r.p, "usd": r.usd} for r in score.runs()]})


def run_show(args: Any) -> int:
    from algent_backend.experiment import runner, store

    if store.exists(f"runs/{args.id}/run.json"):
        prompt = store.path(f"runs/{args.id}/prompt.txt")
        return _emit({"run": store.read_json(f"runs/{args.id}/run.json"), "manifest": store.read_json(f"runs/{args.id}/manifest.json"),
                      "output": store.read_json(f"runs/{args.id}/output.json"), "prompt": prompt.read_text(encoding="utf-8") if prompt.exists() else "",
                      "integrity_problems": runner.verify(args.id)})
    doc = store.read_json(f"questions/{args.id}.json")
    return _emit(doc if doc else {"error": f"no run or question {args.id}"})


def run_branch(args: Any) -> int:
    from algent_backend.experiment import branches, policies

    name, _, ver = args.evidence.partition("@")
    parent = branches.load(args.parent)
    proto = policies.replace_policy(policies.load_protocol(parent.protocol_id), policies.evidence_policy(name, int(ver or 1)), args.name)
    child = branches.fork(parent, args.name, proto)
    return _emit({"branch": child.model_dump(), "protocol": proto.id, "parent_untouched": branches.load(parent.id).protocol_id == parent.protocol_id})


def run_score(args: Any) -> int:
    from algent_backend.experiment import decision, qset, score

    if args.qset:
        return _emit({"forecasts": qset.board(qset.load(args.qset)), "decisions": decision.board()})
    return _emit({**score.scoreboard(), "decisions": decision.board()})


def run_verify(args: Any) -> int:
    from algent_backend.experiment import runner

    problems = runner.verify(args.run_id)
    return _emit({"run": args.run_id, "intact": not problems, "problems": problems})
