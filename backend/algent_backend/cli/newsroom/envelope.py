"""
``newsroom envelope`` - the operating envelope: every register row of docs/architecture/foundation.md measured live, ok / warn / fail
against the budgets in ``ops/envelope_flags.py``. Spends nothing.

    newsroom envelope [--log] [--text]

Prints one JSON document (or, with --text, one line per row). ``--log`` also appends the one-line summary to ~/ops-log.md (the daily timer does
this). Exit code 1 when any row fails.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any


def add_parser(sub: Any) -> None:
    p = sub.add_parser("envelope", help="disk, RAM, journal, stores, R2, backups, feeds, search, spend: each row ok/warn/fail against its budget")
    p.add_argument("--log", action="store_true", help="append the one-line summary to ~/ops-log.md")
    p.add_argument("--text", action="store_true", help="one line per row instead of JSON")
    p.set_defaults(handler=run_envelope)


def run_envelope(args: Any) -> int:
    try:
        from dotenv import load_dotenv

        load_dotenv(Path(__file__).resolve().parents[3] / ".env")
    except ImportError:
        pass
    from algent_backend.ops import envelope

    report = envelope.run()
    if args.log:
        envelope.log(report)
    if args.text:
        for name, r in report["rows"].items():
            print(f"{r['status'].upper():4} {name:28} {r['detail']}")
        print(report["summary"])
    else:
        print(json.dumps(report, indent=2, ensure_ascii=False))
    return 0 if report["ok"] else 1
