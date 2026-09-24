"""
A spending envelope across runs — the runaway guard for unattended work.

Every article already has its own hard cap (``cost.article_scoped``), but nothing capped the
total across runs, so a loop of runs, or one left going after its operator walked away, had no
ceiling at all. An envelope is opened with a dollar limit and a run count, lives on disk, and
is enforced by the rail itself — not by whoever launched it. That is the point: the protection
has to hold after the session that opened it is gone.

Three rules keep it honest:

1. **No envelope, no change.** With no budget file the newsroom runs exactly as before.
2. **A run is charged its whole allowance until it reports back.** A run that claims a slot
   reserves everything left in the envelope as its own hard cap; when it finishes it settles
   at what it actually spent. A run that dies without settling keeps its reservation, so a
   crash can never free money that may already have been spent. ``reconcile`` settles such runs
   from their on-disk report when one exists.
3. **Exhausted means refused.** Out of runs or out of dollars, a new run is refused before it
   spends anything.

Menu builds spend a little and are charged against the dollars, but not counted as runs.
"""

from __future__ import annotations

import json
import os
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

_ENV = "ALGENT_SPEND_BUDGET"
_DEFAULT = Path("runs_data") / "spend_budget.json"


class BudgetExhausted(RuntimeError):
    """The envelope has no runs or no dollars left. Nothing was spent."""


def path() -> Path:
    return Path(os.environ.get(_ENV) or _DEFAULT)


def load(where: Path | None = None) -> dict[str, Any] | None:
    try:
        return json.loads((where or path()).read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None


def _save(state: dict[str, Any], where: Path | None = None) -> None:
    target = where or path()
    target.parent.mkdir(parents=True, exist_ok=True)
    tmp = target.with_suffix(".tmp")
    tmp.write_text(json.dumps(state, indent=2), encoding="utf-8")
    tmp.replace(target)


def open_envelope(limit_usd: float, max_runs: int, *, note: str = "",
                  where: Path | None = None) -> dict[str, Any]:
    state = {
        "limit_usd": round(float(limit_usd), 4), "max_runs": int(max_runs), "note": note,
        "opened_at": datetime.now(UTC).isoformat(), "entries": [],
    }
    _save(state, where)
    return state


def close_envelope(where: Path | None = None) -> None:
    (where or path()).unlink(missing_ok=True)


def committed(state: dict[str, Any]) -> float:
    """Dollars spent or still reserved: settled entries at actual, open ones at their cap plus
    whatever an earlier attempt of the same run already spent (``prior_usd``)."""
    total = 0.0
    for e in state.get("entries") or []:
        total += float(e["usd"]) if e.get("settled") else (
            float(e.get("cap") or 0.0) + float(e.get("prior_usd") or 0.0))
    return round(total, 6)


def record_partial(run_id: str, usd: float, *, where: Path | None = None) -> None:
    """A run is dying mid-flight and will be resumed: bank what it spent, release its cap.

    Without this, a resume reusing the open entry was handed the whole remaining envelope as
    if the dead attempt had cost nothing — harmless by hand, a runaway once resumes are automatic.
    """
    state = load(where)
    if state is None:
        return
    for e in state.get("entries") or []:
        if e.get("run_id") == run_id and not e.get("settled"):
            e["prior_usd"] = round(float(e.get("prior_usd") or 0.0) + max(0.0, float(usd)), 6)
            e["cap"] = 0.0
            _save(state, where)
            return


def runs_used(state: dict[str, Any]) -> int:
    return sum(1 for e in state.get("entries") or [] if e.get("kind") == "run")


def remaining(state: dict[str, Any]) -> float:
    return max(0.0, round(float(state["limit_usd"]) - committed(state), 6))


def claim(run_id: str, *, kind: str = "run", where: Path | None = None) -> float | None:
    """Reserve this run's allowance. Returns its hard cap in dollars, or None with no envelope.

    A second claim by the same run (``newsroom resume``) reuses its entry: it is the same
    article, not a new one, and its earlier reservation is folded back into its allowance.
    """
    state = load(where)
    if state is None:
        return None
    reconcile(where=where)
    state = load(where) or state
    entries = state.setdefault("entries", [])
    mine = next((e for e in entries if e.get("run_id") == run_id and not e.get("settled")), None)
    if mine is None:
        if kind == "run" and runs_used(state) >= int(state["max_runs"]):
            raise BudgetExhausted(
                f"spend envelope: all {state['max_runs']} runs used — open a new envelope to run more")
        mine = {"run_id": run_id, "kind": kind, "cap": 0.0, "usd": 0.0, "settled": False,
                "claimed_at": datetime.now(UTC).isoformat()}
        entries.append(mine)
    mine["cap"] = 0.0
    cap = remaining(state)
    if cap <= 0.0:
        entries.remove(mine)          # refused before spending: it never became a run
        _save(state, where)
        raise BudgetExhausted(
            f"spend envelope: ${state['limit_usd']:.2f} limit reached "
            f"(${committed(state):.2f} spent or reserved)")
    mine["cap"] = cap
    _save(state, where)
    return cap


def settle(run_id: str, usd: float, *, where: Path | None = None) -> None:
    state = load(where)
    if state is None:
        return
    for e in state.get("entries") or []:
        if e.get("run_id") == run_id and not e.get("settled"):
            e.update({"usd": round(float(usd) + float(e.get("prior_usd") or 0.0), 6), "settled": True,
                      "settled_at": datetime.now(UTC).isoformat()})
    _save(state, where)


def reconcile(*, where: Path | None = None, runs_root: Path | None = None) -> int:
    """Settle runs that died after writing a report. Returns how many were settled.

    A run with no report stays reserved at its cap — we cannot know what it spent, and the
    envelope must never assume less than the worst case.
    """
    state = load(where)
    if state is None:
        return 0
    root = runs_root or Path("runs_data") / "newsroom_rail"
    fixed = 0
    for e in state.get("entries") or []:
        if e.get("settled") or e.get("kind") != "run":
            continue
        for report in root.glob(f"*__{e['run_id']}/artifacts/newsroom_rail_report.json"):
            try:
                usd = float(json.loads(report.read_text(encoding="utf-8")).get("total_usd") or 0)
            except (OSError, ValueError, json.JSONDecodeError):
                continue
            e.update({"usd": round(usd + float(e.get("prior_usd") or 0.0), 6), "settled": True,
                      "settled_by": "reconcile"})
            fixed += 1
    if fixed:
        _save(state, where)
    return fixed
