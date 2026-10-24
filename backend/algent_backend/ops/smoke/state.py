"""The last smoke report, kept beside the envelope state, so the doctor row can judge it and the ops-log hears only about changes."""

from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from algent_backend.ops import opslog

from . import flags
from .run import Report


def state_path() -> Path:
    from algent_backend.agent_system.foundation import live_spend

    return live_spend.halt_path().parent / flags.STATE_FILE


def read(path: Path | None = None) -> dict[str, Any]:
    try:
        data = json.loads((path or state_path()).read_text(encoding="utf-8"))
        return data if isinstance(data, dict) else {}
    except (OSError, ValueError):
        return {}


def record(report: Report, *, path: Path | None = None, log: bool = True, home: Path | None = None) -> dict[str, Any]:
    """Save the report's headline. Only production runs are kept (a preview check must not hide a production failure). Writes ``~/ops-log.md`` when the
    verdict changes or the site is still failing (first failure, every failure while it lasts, and the recovery), never for routine green runs."""
    path = path or state_path()
    before = read(path)
    failing = [f"{r.path}: {'; '.join(r.notes)[:90]}" for r in report.results if r.severity == "fail"]
    state = {"at": report.at, "base": report.base, "ok": report.ok, "summary": report.summary(), "failing": failing[:8],
             "since_failure": (before.get("since_failure") or report.at) if not report.ok else None,
             "last_ok_at": report.at if report.ok else before.get("last_ok_at")}
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(state, indent=1), encoding="utf-8")
    except OSError:
        pass
    if log:
        if not report.ok:
            opslog.append("site-smoke", f"FAIL {report.base}: {report.summary()} - " + "; ".join(failing[:4]), home=home)
        elif before and not before.get("ok", True):
            opslog.append("site-smoke", f"recovered {report.base}: {report.summary()} (failing since {before.get('since_failure')})", home=home)
    return state


def age_hours(state: dict[str, Any], now: datetime | None = None) -> float | None:
    try:
        return ((now or datetime.now(UTC)) - datetime.fromisoformat(state["at"])).total_seconds() / 3600
    except (KeyError, ValueError, TypeError):
        return None
