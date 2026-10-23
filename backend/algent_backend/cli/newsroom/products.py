"""
``newsroom products`` - the product registry (ops/products/registry.py): the one place that says what we make, keep, back up, schedule and publish.

    newsroom products table [--write]         the register as a markdown table (--write: refresh it inside docs/architecture/foundation.md)
    newsroom products timers                  "<name>\\t<command>\\t<OnCalendar>" per timer: what infra/server/install_schedules.sh installs
    newsroom products run <job>               what a timer starts: take the job lock, run the job (paid jobs through the spend gates)
    newsroom products runs [--days N] [--json]  the run ledger: per job runs, p50/p95 duration, lock wait, peak RSS, skips (ops/jobq)
    newsroom products capacity [--json] [--new-desk JOB]  lock busy share, tight windows, memory floor, what one more desk costs, the split rule
    newsroom products check [--text]          validate the registry and judge this machine against it (also embedded in `newsroom doctor`)
    newsroom products contract [--write]      the JSON the site reads (routes, publications, refresh cadence); --write refreshes sites/ohmega-monster/lib/products.json
    newsroom products housekeeping [--apply]  expire the fetch cache and old per-job run logs (daily timer; dry run without --apply)

Free; no model.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any

_REPO = Path(__file__).resolve().parents[4]
FOUNDATION = _REPO / "docs" / "architecture" / "foundation.md"
CONTRACT = _REPO / "sites" / "ohmega-monster" / "lib" / "products.json"


def add_parser(sub: Any) -> None:
    p = sub.add_parser("products", help="the product registry: table, timers, run a job, check this machine, site contract, housekeeping")
    verbs = p.add_subparsers(dest="products_cmd", required=True)
    t = verbs.add_parser("table", help="the register as markdown")
    t.add_argument("--write", action="store_true", help="refresh the table inside docs/architecture/foundation.md")
    t.set_defaults(handler=run_table)
    verbs.add_parser("timers", help="name, command, OnCalendar per timer (tab separated)").set_defaults(handler=run_timers)
    r = verbs.add_parser("run", help="run one registered job (what its systemd timer starts)")
    r.add_argument("job")
    r.set_defaults(handler=run_run)
    u = verbs.add_parser("runs", help="the run ledger: durations, lock waits, skips, peak memory per job")
    u.add_argument("--days", type=float, default=7)
    u.add_argument("--json", action="store_true")
    u.set_defaults(handler=run_runs)
    cap = verbs.add_parser("capacity", help="busy share, tight windows, memory floor, one-more-desk projection, split rule")
    cap.add_argument("--json", action="store_true")
    cap.add_argument("--new-desk", default="ai-daily", help="the job whose size the projected desk copies (default ai-daily)")
    cap.set_defaults(handler=run_capacity)
    c = verbs.add_parser("check", help="validate the registry and judge this machine against it")
    c.add_argument("--text", action="store_true", help="one line per row instead of JSON")
    c.set_defaults(handler=run_check)
    k = verbs.add_parser("contract", help="the JSON contract the site reads")
    k.add_argument("--write", action="store_true", help="write sites/ohmega-monster/lib/products.json")
    k.set_defaults(handler=run_contract)
    h = verbs.add_parser("housekeeping", help="expire the fetch cache and old per-job run logs")
    h.add_argument("--apply", action="store_true", help="delete (default: report only)")
    h.set_defaults(handler=run_housekeeping)


def run_table(args: Any) -> int:
    from algent_backend.ops.products import views

    if args.write:
        FOUNDATION.write_text(views.embed(FOUNDATION.read_text(encoding="utf-8")), encoding="utf-8")
        print(f"updated {FOUNDATION}")
    else:
        print(views.table_markdown())
    return 0


def run_timers(_args: Any) -> int:
    from algent_backend.ops.products import views

    for line in views.timer_lines():
        print(line)
    return 0


def run_run(args: Any) -> int:
    from algent_backend.ops.products import run

    return run.run_job(args.job)


def run_runs(args: Any) -> int:
    from algent_backend.ops.jobq import render

    data = render.runs_data(days=args.days)
    print(json.dumps(data, indent=2) if args.json else render.runs_text(data))
    return 0


def run_capacity(args: Any) -> int:
    from algent_backend.ops.jobq import capacity, render

    rep = capacity.report(new_desk=args.new_desk)
    print(json.dumps(rep, indent=2, default=str) if args.json else render.capacity_text(rep))
    return 0


def run_check(args: Any) -> int:
    try:
        from dotenv import load_dotenv

        load_dotenv(_REPO / ".env")
    except ImportError:
        pass
    from algent_backend.ops.products import check

    report = check.run()
    if args.text:
        for name, r in report["rows"].items():
            print(f"{r['status'].upper():4} {name:20} {r['detail']}")
        print(report["summary"])
    else:
        print(json.dumps(report, indent=2, ensure_ascii=False))
    return 0 if report["ok"] else 1


def contract_text() -> str:
    from algent_backend.ops.products import views

    return json.dumps(views.site_contract(), indent=2, ensure_ascii=False) + "\n"


def run_contract(args: Any) -> int:
    if args.write:
        CONTRACT.write_text(contract_text(), encoding="utf-8")
        print(f"wrote {CONTRACT}", file=sys.stderr)
    else:
        print(contract_text(), end="")
    return 0


def run_housekeeping(args: Any) -> int:
    from algent_backend.ops import housekeeping

    print(json.dumps(housekeeping.run(apply=args.apply), indent=2))
    return 0
