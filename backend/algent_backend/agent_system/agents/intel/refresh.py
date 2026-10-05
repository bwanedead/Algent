"""
Refresh the sensing layers before the desk writes, so the daily reads today's numbers and words.

Instruments fetch is free HTTP; statements collection is free HTTP plus one cheap-model extraction per
NEW transcript (extraction skips transcripts it already did, so a rerun costs nothing). Each layer is
best-effort and isolated: a layer that fails is recorded in the report and the day goes on with what
the stores already hold. The collectors are injectable so tests (and any caller) stay offline.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

MAX_REPORTED_ERRORS = 5          # a report line per failure is noise; the first few say what is wrong


def _instruments() -> dict[str, Any]:
    from algent_backend.instruments.collect import collect

    out = collect()
    problems = [{"id": r["id"], "status": r["status"], "error": r.get("error", "")[:160]}
                for r in out["series"] if r["status"] != "ok"]
    return {k: out[k] for k in ("ok", "blocked", "error", "skipped", "as_of")} | {"problems": problems[:MAX_REPORTED_ERRORS]}


def _statements(context: Any, model_spec: Any) -> dict[str, Any]:
    from algent_backend.agent_system.agents.statements import collect, extract

    feeds = collect.collect()
    out: dict[str, Any] = {"transcripts_collected": sum(f["collected"] for f in feeds),
                           "feed_errors": [f"{f.get('feed', '?')}: {e}" for f in feeds
                                           for e in f.get("errors", [])][:MAX_REPORTED_ERRORS]}
    # The reported lane: leaders the official feeds cannot reach (Zelensky, Baltic and Polish leaders…) as quoted
    # by trusted outlets, budgeted inside the lane. Runs before extraction so its articles are extracted with the
    # rest; a failure costs only this lane.
    try:
        from algent_backend.agent_system.agents.statements import reported

        from .heat import registry

        live = [f"{t.get('name', '')}. {t.get('description', '')}" for t in registry().values()
                if isinstance(t, dict) and t.get("state") in ("new", "active") and t.get("domain") == "geopolitics"]
        out["reported"] = reported.collect_reported(theaters=live)
    except Exception as exc:  # noqa: BLE001 - the official record still refreshes without it
        out["reported"] = {"error": f"{type(exc).__name__}: {str(exc)[:200]}"}
    out["extraction"] = extract.extract_pending(context, None, model_spec)
    out["extraction"]["errors"] = out["extraction"].get("errors", [])[:MAX_REPORTED_ERRORS]
    return out


def refresh(context: Any, model_spec: Any, *, instruments: Callable[[], dict] = _instruments,
            statements: Callable[[Any, Any], dict] = _statements) -> dict[str, Any]:
    """Run both layers' refresh; returns ``{"instruments": ..., "statements": ...}`` where a layer that
    raised reports ``{"error": "..."}`` instead. Never raises."""
    report: dict[str, Any] = {}
    for name, call in (("instruments", lambda: instruments()), ("statements", lambda: statements(context, model_spec))):
        try:
            report[name] = call()
        except Exception as exc:  # noqa: BLE001 - a layer being down must never fail the day
            report[name] = {"error": f"{type(exc).__name__}: {str(exc)[:200]}"}
    return report
