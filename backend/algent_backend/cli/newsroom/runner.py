"""
``newsroom runner`` — which machine runs paid work and publishes (server OR laptop, never both).

    newsroom runner status
    newsroom runner claim [--force] [--note TEXT]
    newsroom runner release [--force]

See ``data_backup/runner.py`` for the design and ``docs/guides/runner-handover.md`` for the procedure.
"""

from __future__ import annotations

import json
from typing import Any

from algent_backend.data_backup import runner


def add_parser(sub: Any) -> None:
    p = sub.add_parser("runner", help="who runs paid work + publishes: status / claim / release")
    verbs = p.add_subparsers(dest="runner_cmd", required=True)
    verbs.add_parser("status", help="show the current runner").set_defaults(handler=run_status)
    c = verbs.add_parser("claim", help="make THIS machine the runner")
    c.add_argument("--force", action="store_true", help="take over from a holder that is gone")
    c.add_argument("--note", default="")
    c.set_defaults(handler=run_claim)
    r = verbs.add_parser("release", help="give the claim up (before handing to the other machine)")
    r.add_argument("--force", action="store_true", help="release a claim held by a machine that is gone")
    r.set_defaults(handler=run_release)


def run_status(_args: Any) -> int:
    print(json.dumps(runner.status(), indent=2))
    return 0


def run_claim(args: Any) -> int:
    out = runner.claim(force=args.force, note=args.note)
    print(json.dumps(out, indent=2))
    return 0 if out["claimed"] else 1


def run_release(args: Any) -> int:
    out = runner.release(force=args.force)
    print(json.dumps(out, indent=2))
    return 0 if out["released"] else 1
