"""
Append-only observation store — one JSONL file per series.

    <root>/series/<series_id>.jsonl      # one Observation per line, in the order learned

The log is the truth; the current picture is a projection (same stance as the Pulse log). A fetch
appends a line only for a period never seen before, or for a period whose published value CHANGED
(that line carries ``revised=True``) — an unchanged re-fetch writes nothing, and no line is ever
edited or removed. ``history`` projects "latest line per period", so what we believed on any past
day is recoverable by filtering ``fetched_at``.

The root resolves like the intel store: ``ALGENT_INSTRUMENTS_STORE`` or ``instruments_store`` under
the working directory.
"""

from __future__ import annotations

import os
from pathlib import Path

from pydantic import BaseModel

from .contracts import Observation, period_date

_STORE_ENV = "ALGENT_INSTRUMENTS_STORE"
_DEFAULT_DIR = "instruments_store"


class AppendResult(BaseModel):
    new: int = 0
    revised: int = 0
    unchanged: int = 0


def store_dir() -> Path:
    return Path(os.environ.get(_STORE_ENV) or _DEFAULT_DIR)


def _path(series_id: str) -> Path:
    return store_dir() / "series" / f"{series_id}.jsonl"


def log(series_id: str) -> list[Observation]:
    """Every line ever written, oldest first."""
    path = _path(series_id)
    if not path.is_file():
        return []
    return [Observation.model_validate_json(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def history(series_id: str) -> list[Observation]:
    """The projection: the latest line per period, ordered by period."""
    latest = {o.period: o for o in log(series_id)}
    return sorted(latest.values(), key=lambda o: period_date(o.period))


def append(series_id: str, observations: list[Observation]) -> AppendResult:
    """Write the new and revised periods from ``observations``; skip what is already known."""
    known = {o.period: o.value for o in history(series_id)}
    batch = {o.period: o for o in observations}            # a period repeated in one batch: last wins
    lines, result = [], AppendResult()
    for period in sorted(batch, key=period_date):
        obs = batch[period]
        if period not in known:
            result.new += 1
        elif obs.value != known[period]:
            obs, result.revised = obs.model_copy(update={"revised": True}), result.revised + 1
        else:
            result.unchanged += 1
            continue
        lines.append(obs.model_dump_json())
    if lines:
        path = _path(series_id)
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("a", encoding="utf-8", newline="\n") as fh:
            fh.write("\n".join(lines) + "\n")
    return result


def stored_ids() -> list[str]:
    root = store_dir() / "series"
    return sorted(p.stem for p in root.glob("*.jsonl")) if root.is_dir() else []
