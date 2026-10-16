"""
The tick — the hourly job that turns finished hour files into baselines, anomalies, daily rollups and the site's table.

Called by the timer runner (``live/runner.py``, every few minutes; it does nothing until an hour has settled) and by
``newsroom live memory tick``. It is the only writer of the baselines and the state, serialised by a lock file, and it is
resumable: the state's ``cursor`` is the last hour processed, and every pass handles the settled hours after it, in order.

    state.json          {cursor, rolled, runs, closed}   the detector's open runs and recently closed anomalies
    baseline_<layer>.bin.gz                              the learned normals (``baseline.py``)
    anomalies/log.jsonl                                  append-only open / close events
    anomalies/current.json                               the current picture (``anomalies.collapse``)

Forward-only: the first pass starts at the oldest hour file there is; nothing before the service started is invented.
"""

from __future__ import annotations

import os
import time
from contextlib import contextmanager
from datetime import datetime, timedelta, timezone
from typing import Any, Callable, Iterator

from .. import store
from . import anomalies, flags, hours
from .baseline import Baseline
from .daily import rollup_day
from .detect import Detector, Run

#: A pass touches only hours that ended at least this long ago: the stream service writes an hour's file at its first
#: board refresh of the NEXT hour, so a younger hour may simply not be written yet (and would be mistaken for missing).
SETTLE_SECONDS = 600
#: Hours handled in one pass (a catch-up after the server was down); the rest wait for the next pass.
MAX_HOURS_PER_PASS = 336
STALE_LOCK_S = 1800


class Busy(RuntimeError):
    pass


@contextmanager
def _lock() -> Iterator[None]:
    path = hours.root() / "tick.lock"
    path.parent.mkdir(parents=True, exist_ok=True)
    for _ in range(2):
        try:
            os.close(os.open(path, os.O_CREAT | os.O_EXCL | os.O_WRONLY))
            break
        except FileExistsError:
            if time.time() - path.stat().st_mtime > STALE_LOCK_S:
                path.unlink(missing_ok=True)
                continue
            raise Busy("another memory tick is running") from None
    else:
        raise Busy("could not take the memory tick lock")
    try:
        yield
    finally:
        path.unlink(missing_ok=True)


def _state_path():
    return hours.root() / "state.json"


def _baseline_path(layer: str):
    return hours.root() / f"baseline_{layer}.bin.gz"


def load_state() -> dict[str, Any]:
    st = store._read(_state_path(), {})
    return {"cursor": st.get("cursor"), "rolled": st.get("rolled"), "runs": st.get("runs", {}), "closed": st.get("closed", []),
            "screened": st.get("screened", {})}


def tick(now: float | None = None, *, publish: bool = True, connect: Callable[[], Any] | None = None) -> dict[str, Any]:
    """One pass. Returns a small account (hours processed, events, screened artefacts, rollups, publish result). Never raises."""
    try:
        with _lock():
            return _tick(time.time() if now is None else now, publish, connect)
    except Busy as exc:
        return {"busy": str(exc)}
    except Exception as exc:  # noqa: BLE001 - memory must never cost a feed run
        return {"error": f"{type(exc).__name__}: {str(exc)[:160]}"}


def _pending(cursor: int | None, settled_before: int) -> list[int]:
    stored = hours.stored_hours()
    if not stored:
        return []
    first = stored[0] if cursor is None else cursor + 1
    return list(range(max(first, stored[0]), settled_before))[:MAX_HOURS_PER_PASS]


def _tick(now: float, publish: bool, connect: Callable[[], Any] | None) -> dict[str, Any]:
    state = load_state()
    settled_before = hours.hour_of(now - SETTLE_SECONDS)                 # hours strictly before this are complete
    todo = _pending(state["cursor"], settled_before)
    # the baselines are megabytes: read them only when an hour is actually to be processed (most timer runs find none)
    baselines = {layer: Baseline.load(layer, _baseline_path(layer)) for layer in ("ship", "air", "fire")} if todo else {}
    det = Detector(baselines, {k: Run.from_json(v) for k, v in state["runs"].items()})
    opened = closed = 0
    screened: dict[str, int] = dict(state["screened"])
    closed_list = [anomalies.Anomaly.model_validate(d) for d in state["closed"]]
    for h in todo:
        for ev in det.step(hours.read_hour(h)):
            a = anomalies.from_run(ev.run, ev.end)
            anomalies.log_event(ev.kind, a, hours.iso_hour(h))
            if ev.kind == "open":
                opened += 1
            else:
                closed += 1
                closed_list.append(a)
        for reason, n in det.screened.items():
            screened[reason] = screened.get(reason, 0) + n
    horizon = (datetime.fromtimestamp(now, tz=timezone.utc) - timedelta(days=flags.RETAIN_DAYS)).isoformat(timespec="seconds")
    closed_list = [a for a in closed_list if (a.ends_at or "") >= horizon]
    out: dict[str, Any] = {"hours": len(todo), "opened": opened, "closed": closed, "screened": dict(det.screened)}

    if todo:
        for layer, bl in baselines.items():
            bl.forget(hours.day_of(todo[-1]))
            bl.save(_baseline_path(layer))
        state["cursor"] = todo[-1]
    out["rollups"] = _rollups(state, now)
    active = [anomalies.from_run(r) for r in det.runs.values() if r.confirmed]
    current = anomalies.collapse(active + closed_list)
    if todo or not (hours.root() / "anomalies" / "current.json").exists():
        anomalies.write_current(current, hours.iso_hour(settled_before))
    if todo and publish:
        out["publish"] = anomalies.publish(current, connect=connect)
    out["active"] = len(active)
    store._write(_state_path(), {"cursor": state["cursor"], "rolled": state["rolled"], "screened": screened,
                                 "runs": {k: r.to_json() for k, r in det.runs.items()}, "closed": [a.model_dump() for a in closed_list]})
    hours.prune(now)
    return out


def _rollups(state: dict[str, Any], now: float) -> dict[str, int]:
    """Roll every completed UTC day (after the last one rolled) into the instruments store."""
    stored = hours.stored_hours()
    if not stored:
        return {}
    last_done = hours.day_of(hours.hour_of(now - SETTLE_SECONDS)) - 1       # yesterday and earlier are complete
    day = (state["rolled"] + 1) if state["rolled"] is not None else hours.day_of(stored[0])
    written = days = 0
    while day <= last_done:
        written += rollup_day(day).get("written", 0)
        state["rolled"] = day
        day += 1
        days += 1
    return {"days": days, "written": written}


def status() -> dict[str, Any]:
    """What memory holds: hour files and their size on disk, each layer's places and maturity, the cursor, open anomalies, screened artefacts."""
    st = load_state()
    layers = {}
    for layer in ("ship", "air", "fire"):
        bl = Baseline.load(layer, _baseline_path(layer))
        p = _baseline_path(layer)
        layers[layer] = {"places": len(bl.index), "observed_hours": bl.observed, "mature": bl.mature(),
                         "file_bytes": p.stat().st_size if p.exists() else 0}
    stored = hours.stored_hours()
    return {"hours_on_disk": len(stored), "hours_bytes": hours.disk_bytes(),
            "first_hour": hours.iso_hour(stored[0]) if stored else None, "cursor": hours.iso_hour(st["cursor"]) if st["cursor"] is not None else None,
            "baselines": layers, "open_runs": len(st["runs"]), "confirmed": sum(1 for r in st["runs"].values() if r.get("confirmed")),
            "screened_total": st["screened"], "current": len(anomalies.read_current())}
