"""
``newsroom doctor`` — readiness check for THIS machine (server or laptop); spends nothing.

    newsroom doctor

One JSON document: ok/warn/fail per check plus a summary line. Exit code 1 when any check fails.
See ``ops/doctor.py`` and ``docs/guides/runner-handover.md``.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any


def add_parser(sub: Any) -> None:
    sub.add_parser("doctor", help="is this machine ready to be the runner? (keys, db, search, reads, harnesses)"
                   ).set_defaults(handler=run_doctor)


def run_doctor(_args: Any) -> int:
    try:
        from dotenv import load_dotenv

        load_dotenv(Path(__file__).resolve().parents[3] / ".env")
    except ImportError:
        pass
    from algent_backend.ops import doctor

    report = doctor.run_checks()
    print(json.dumps(report, indent=2))
    return 0 if report["ok"] else 1
