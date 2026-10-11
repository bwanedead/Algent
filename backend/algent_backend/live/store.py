"""
Live store — what the collectors keep on disk between runs.

    <root>/events/<feed>.json     the CURRENT events of a feed (a snapshot, replaced each good run)
    <root>/status.json            per feed: last attempt, last success, error or "needs KEY", event count
    <root>/running_<owner>.json   per ``live_*`` series: the day currently being measured (partial)

Numbers live in the instruments store, not here, and only COMPLETED days: a day still being measured sits in
``running.json`` until UTC midnight passes and is then appended as that day's observation. That keeps a half-counted
today from ever reading as a collapse in the moves math. Each writer (``timers``, the ``ais`` service) owns its own
running file, so the always-on service and the timers never overwrite each other. Root: ``ALGENT_LIVE_STORE`` or ``live_store``.
"""

from __future__ import annotations

import json
import os
from datetime import date
from pathlib import Path
from typing import Any

from algent_backend.instruments import store as istore
from algent_backend.instruments.contracts import Observation, now_iso

from .contracts import LiveEvent, Stat

_ENV = "ALGENT_LIVE_STORE"
_DEFAULT = "live_store"


def root() -> Path:
    return Path(os.environ.get(_ENV) or _DEFAULT)


def _read(path: Path, default: Any) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return default


def _write(path: Path, doc: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(doc, ensure_ascii=False, indent=1), encoding="utf-8")
    os.replace(tmp, path)


# ── events ────────────────────────────────────────────────────────────────────────────────────
def write_events(feed: str, events: list[LiveEvent]) -> None:
    _write(root() / "events" / f"{feed}.json", [e.model_dump() for e in events])


def read_events(feed: str | None = None) -> list[LiveEvent]:
    names = [feed] if feed else sorted(p.stem for p in (root() / "events").glob("*.json"))
    return [LiveEvent.model_validate(d) for n in names for d in _read(root() / "events" / f"{n}.json", [])]


# ── small documents shared between processes (gate counts, summary, fire heat) ─────────────────
def write_doc(name: str, doc: Any) -> None:
    _write(root() / "docs" / f"{name}.json", doc)


def read_doc(name: str) -> Any:
    return _read(root() / "docs" / f"{name}.json", None)


# ── status ────────────────────────────────────────────────────────────────────────────────────
def read_status() -> dict[str, dict[str, Any]]:
    return _read(root() / "status.json", {})


def record_status(feed: str, **fields: Any) -> None:
    status = read_status()
    status[feed] = {**status.get(feed, {}), **fields}
    _write(root() / "status.json", status)


# ── running day -> instrument series ──────────────────────────────────────────────────────────
def _running(owner: str) -> dict[str, dict[str, Any]]:
    return _read(root() / f"running_{owner}.json", {})


def running() -> dict[str, dict[str, Any]]:
    """{series_id: {period, value}} — the days being measured right now (partial), from every owner."""
    return {**_running("timers"), **_running("ais")}


def apply_stats(stats: list[Stat], today: date, owner: str = "timers") -> dict[str, int]:
    """Fold readings into the running day; any series whose running day has ended is appended to the
    instruments store as that day's final observation. Returns ``{"completed": n, "running": n}``."""
    run, completed = _running(owner), 0
    for st in stats:
        cur = run.get(st.series_id)
        if cur and cur["period"] != today.isoformat():
            completed += _complete(st.series_id, cur)
            cur = None
        value = st.value if st.mode == "set" or not cur else max(st.value, cur["value"])
        run[st.series_id] = {"period": today.isoformat(), "value": value}
    for sid, cur in list(run.items()):           # series the feed did not mention today still close their old day
        if cur["period"] != today.isoformat():
            completed += _complete(sid, cur)
            del run[sid]
    _write(root() / f"running_{owner}.json", run)
    return {"completed": completed, "running": len(run)}


def _complete(series_id: str, cur: dict[str, Any]) -> int:
    from algent_backend.instruments.catalog import get_series

    s = get_series(series_id)
    res = istore.append(series_id, [Observation(series_id=series_id, period=cur["period"], value=float(cur["value"]),
                                                fetched_at=now_iso(), source_url=s.source_url)])
    return res.new + res.revised
