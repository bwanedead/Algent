"""
Append-only store — one JSONL file per indicator, plus a leaders log.

    <root>/obs/<indicator_id>.jsonl      # one Observation per line, in the order learned
    <root>/leaders.jsonl                 # one Leaders snapshot per line

Same discipline as ``instruments/store.py``: the log is the truth, the current picture is a projection.
A fetch appends a line only for a (country, year) never seen, or whose published value CHANGED (that
line carries ``revised=True``); an unchanged re-fetch writes nothing and no line is ever edited or
removed. ``history`` projects the latest line per (country, year); ``latest`` the newest year per
country. Leaders: a line is appended when a country's two office-holders changed, or when the last
line for it is older than ``LEADERS_RECHECK_DAYS`` (so "as of" stays honest without a line per run).

Root: env ``ALGENT_ACTORS_STORE`` or ``actors_store`` under the working directory.
"""

from __future__ import annotations

import os
from datetime import datetime, timedelta
from pathlib import Path

from pydantic import BaseModel

from .contracts import Leaders, Observation, TradeRanking

_STORE_ENV = "ALGENT_ACTORS_STORE"
_DEFAULT_DIR = "actors_store"
LEADERS_RECHECK_DAYS = 30


class AppendResult(BaseModel):
    new: int = 0
    revised: int = 0
    unchanged: int = 0


def store_dir() -> Path:
    return Path(os.environ.get(_STORE_ENV) or _DEFAULT_DIR)


def _obs_path(indicator_id: str) -> Path:
    return store_dir() / "obs" / f"{indicator_id}.jsonl"


def _lines(path: Path) -> list[str]:
    return [ln for ln in path.read_text(encoding="utf-8").splitlines() if ln.strip()] if path.is_file() else []


def _append_lines(path: Path, lines: list[str]) -> None:
    if lines:
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("a", encoding="utf-8", newline="\n") as fh:
            fh.write("\n".join(lines) + "\n")


def log(indicator_id: str) -> list[Observation]:
    """Every line ever written, oldest first."""
    return [Observation.model_validate_json(ln) for ln in _lines(_obs_path(indicator_id))]


def history(indicator_id: str) -> list[Observation]:
    """The projection: the latest line per (country, year), ordered by country then year."""
    latest = {(o.iso2, o.year): o for o in log(indicator_id)}
    return [latest[k] for k in sorted(latest)]


def latest(indicator_id: str) -> dict[str, Observation]:
    """Newest year per country."""
    out: dict[str, Observation] = {}
    for o in history(indicator_id):
        if o.iso2 not in out or o.year > out[o.iso2].year:
            out[o.iso2] = o
    return out


def append(indicator_id: str, observations: list[Observation]) -> AppendResult:
    """Write the new and revised readings from ``observations``; skip what is already known."""
    known = {(o.iso2, o.year): o.value for o in history(indicator_id)}
    batch = {(o.iso2, o.year): o for o in observations}        # a key repeated in one batch: last wins
    lines, result = [], AppendResult()
    for key in sorted(batch):
        obs = batch[key]
        if key not in known:
            result.new += 1
        elif obs.value != known[key]:
            obs, result.revised = obs.model_copy(update={"revised": True}), result.revised + 1
        else:
            result.unchanged += 1
            continue
        lines.append(obs.model_dump_json())
    _append_lines(_obs_path(indicator_id), lines)
    return result


def stored_ids() -> list[str]:
    root = store_dir() / "obs"
    return sorted(p.stem for p in root.glob("*.jsonl")) if root.is_dir() else []


# --- ranked trade ---------------------------------------------------------------------------------
def _trade_path() -> Path:
    return store_dir() / "trade.jsonl"


def trade_log() -> list[TradeRanking]:
    return [TradeRanking.model_validate_json(ln) for ln in _lines(_trade_path())]


def latest_trade() -> dict[tuple[str, str], TradeRanking]:
    """(iso2, flow) -> the newest year's ranking (later lines win within a year)."""
    out: dict[tuple[str, str], TradeRanking] = {}
    for r in trade_log():
        k = (r.iso2, r.flow)
        if k not in out or r.year >= out[k].year:
            out[k] = r
    return out


def append_trade(rows: list[TradeRanking]) -> AppendResult:
    """Append a ranking for each (country, flow, year) never seen, or whose lines changed; same discipline as
    ``append``: an unchanged re-fetch writes nothing."""
    known = {(r.iso2, r.flow, r.year): r for r in trade_log()}
    result, lines = AppendResult(), []
    for row in rows:
        prev = known.get((row.iso2, row.flow, row.year))
        if prev is None:
            result.new += 1
        elif (prev.total, prev.products, prev.partners) != (row.total, row.products, row.partners):
            row, result.revised = row.model_copy(update={"revised": True}), result.revised + 1
        else:
            result.unchanged += 1
            continue
        lines.append(row.model_dump_json())
    _append_lines(_trade_path(), lines)
    return result


def series(indicator_id: str, iso2: str) -> list[tuple[int, float]]:
    """One country's annual readings of an indicator, oldest first."""
    return [(o.year, o.value) for o in history(indicator_id) if o.iso2 == iso2]


# --- leaders ------------------------------------------------------------------------------------
def _leaders_path() -> Path:
    return store_dir() / "leaders.jsonl"


def leaders_log() -> list[Leaders]:
    return [Leaders.model_validate_json(ln) for ln in _lines(_leaders_path())]


def latest_leaders() -> dict[str, Leaders]:
    return {row.iso2: row for row in leaders_log()}            # later lines win


def _holders(row: Leaders) -> tuple[str, str]:
    return (row.head_of_state.id or row.head_of_state.name if row.head_of_state else "",
            row.head_of_government.id or row.head_of_government.name if row.head_of_government else "")


def append_leaders(rows: list[Leaders]) -> AppendResult:
    """Append a snapshot per country whose office-holders changed, or whose last line is stale."""
    last, result, lines = latest_leaders(), AppendResult(), []
    for row in rows:
        prev = last.get(row.iso2)
        if prev is None:
            result.new += 1
        elif _holders(prev) != _holders(row):
            result.revised += 1
        elif _age(prev.fetched_at, row.fetched_at) >= timedelta(days=LEADERS_RECHECK_DAYS):
            result.unchanged += 1                              # re-confirmed: a fresh as-of, nothing changed
        else:
            result.unchanged += 1
            continue
        lines.append(row.model_dump_json())
    _append_lines(_leaders_path(), lines)
    return result


def _age(older: str, newer: str) -> timedelta:
    try:
        return datetime.fromisoformat(newer) - datetime.fromisoformat(older)
    except ValueError:
        return timedelta(0)


def data_as_of() -> str:
    """Newest ``fetched_at`` date across the store ("" when empty): the build date a published page can carry
    without a wall clock, so an unchanged store publishes byte-identical files."""
    newest = ""
    for ind in stored_ids():
        lines = _lines(_obs_path(ind))                          # appended in time order: the last line is the newest
        if lines:
            newest = max(newest, Observation.model_validate_json(lines[-1]).fetched_at)
    return newest[:10]

