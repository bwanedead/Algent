"""
Markets store on disk. Root: ``ALGENT_MARKETS_STORE`` or ``markets_store``. Everything is append-only JSON lines: history is never rewritten,
so the record cannot be quietly improved after the fact.

    markets.jsonl     one Market REVISION per line (a changed market is a new line; the last line of an id wins)
    snapshots.jsonl   one price Snapshot per line (live passes and the CLOB history backfill)
    forecasts.jsonl   one Forecast per line: OURS, immutable once written
    trades.jsonl      the RULE book's paper trades: open / mark / settle (a position is a projection of its lines)
    decisions.jsonl   the TRADER's ledger: every decision (buy / sell / hold / settle) with its rationale and any guard clips
    equity.jsonl      one EquityPoint per book per day (the equity curves)
    gaps.jsonl        what the bots looked for and the corpus did not hold (gaps.py); gap_fills.jsonl the research runs those asks became
    research_trace.jsonl  one line per forecast / decision: queries, result ids, cited ids, tokens, cost, latency (trace.py; pruned by age)
    day_runs.jsonl    one DayRun per run of the day book: the full tool trace, orders, cost (day.py; pruned by age)
    status.json       the last pass: when, what it found, what failed
"""

from __future__ import annotations

import json
import os
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import TypeVar

from pydantic import BaseModel

from . import flags
from .contracts import DayRun, Decision, EquityPoint, Forecast, Gap, GapFill, Market, Snapshot, Trace, Trade

_ENV = "ALGENT_MARKETS_STORE"
M = TypeVar("M", bound=BaseModel)


def root() -> Path:
    return Path(os.environ.get(_ENV) or "markets_store")


def now_iso() -> str:
    return datetime.now(UTC).isoformat(timespec="seconds")


def parse_iso(text: str) -> datetime | None:
    try:
        d = datetime.fromisoformat(text.replace("Z", "+00:00"))
    except (ValueError, AttributeError):
        return None
    return d if d.tzinfo else d.replace(tzinfo=UTC)


def _read(name: str, model: type[M]) -> list[M]:
    try:
        lines = (root() / name).read_text(encoding="utf-8").splitlines()
    except OSError:
        return []
    out = []
    for line in lines:
        try:
            out.append(model.model_validate_json(line))
        except ValueError:
            continue                                # a torn line must not hide the rest
    return out


def _append(name: str, rows: list[BaseModel]) -> None:
    if not rows:
        return
    path = root() / name
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8", newline="\n") as fh:
        fh.write("\n".join(r.model_dump_json() for r in rows) + "\n")


# ── markets ──────────────────────────────────────────────────────────────────────────────────────
def markets() -> dict[str, Market]:
    """The latest revision of every market."""
    return {m.id: m for m in _read("markets.jsonl", Market)}


def save_markets(rows: list[Market]) -> dict[str, int]:
    """Append a revision for each new market or one whose content changed (volume/liquidity drift alone is not a change)."""
    have, now, out, new, changed = markets(), now_iso(), [], 0, 0
    skip = {"first_seen", "updated_at", "volume", "liquidity"}
    for m in rows:
        old = have.get(m.id)
        m = m.model_copy(update={"first_seen": old.first_seen if old else now, "updated_at": now})
        if old is not None and old.model_dump(exclude=skip) == m.model_dump(exclude=skip):
            continue
        new, changed = new + (old is None), changed + (old is not None)
        out.append(m)
    _append("markets.jsonl", out)
    return {"new": new, "changed": changed}


# ── snapshots ────────────────────────────────────────────────────────────────────────────────────
def snapshots(market_id: str | None = None) -> list[Snapshot]:
    rows = _read("snapshots.jsonl", Snapshot)
    return [s for s in rows if market_id is None or s.market_id == market_id]


def snapshots_by_market() -> dict[str, list[Snapshot]]:
    out: dict[str, list[Snapshot]] = {}
    for s in snapshots():
        out.setdefault(s.market_id, []).append(s)
    for rows in out.values():
        rows.sort(key=lambda s: s.at)
    return out


def append_snapshots(rows: list[Snapshot]) -> None:
    _append("snapshots.jsonl", rows)


def due_for_snapshot(by_market: dict[str, list[Snapshot]], market_id: str, now: datetime) -> bool:
    live = [s for s in by_market.get(market_id, []) if s.source == "live"]
    last = parse_iso(live[-1].at) if live else None
    return last is None or (now - last) >= timedelta(hours=flags.SNAPSHOT_MIN_GAP_H)


def price_at(rows: list[Snapshot], at: str, *, max_age_h: float | None = None) -> Snapshot | None:
    """The last snapshot at or before ``at`` (sorted ``rows``), if not older than ``max_age_h`` (default ``flags.SNAPSHOT_MAX_AGE_H``)."""
    t = parse_iso(at)
    if t is None:
        return None
    best = None
    for s in rows:
        st = parse_iso(s.at)
        if st is not None and st <= t:
            best = s
    bt = parse_iso(best.at) if best else None
    limit = timedelta(hours=flags.SNAPSHOT_MAX_AGE_H if max_age_h is None else max_age_h)
    return best if best is not None and bt is not None and t - bt <= limit else None


# ── forecasts and trades ─────────────────────────────────────────────────────────────────────────
def forecasts() -> list[Forecast]:
    return _read("forecasts.jsonl", Forecast)


def append_forecast(f: Forecast) -> None:
    _append("forecasts.jsonl", [f])


def trades() -> list[Trade]:
    return _read("trades.jsonl", Trade)


def append_trades(rows: list[Trade]) -> None:
    _append("trades.jsonl", rows)


def decisions(book: str | None = "daily") -> list[Decision]:
    """The ledger of one book (default the daily trader; lines written before the fast book existed have ``book`` "daily"); ``None`` = every book."""
    rows = _read("decisions.jsonl", Decision)
    return rows if book is None else [d for d in rows if d.book == book]


def append_decisions(rows: list[Decision]) -> None:
    _append("decisions.jsonl", rows)


def equity_points() -> list[EquityPoint]:
    return _read("equity.jsonl", EquityPoint)


def append_equity(rows: list[EquityPoint]) -> None:
    """Append points for days a book has no point yet: a day's mark is written once and never replaced."""
    have = {(e.book, e.day) for e in equity_points()}
    _append("equity.jsonl", [e for e in rows if (e.book, e.day) not in have])


# ── research traces and gaps ─────────────────────────────────────────────────────────────────────
def traces() -> list[Trace]:
    return _read("research_trace.jsonl", Trace)


def append_traces(rows: list[Trace]) -> None:
    _append("research_trace.jsonl", rows)


def prune_traces(now: datetime | None = None) -> int:
    """Drop trace lines older than ``flags.TRACE_KEEP_DAYS`` (the only line type ever pruned: observability, not the scored record). Returns how many."""
    now = now or datetime.now(UTC)
    return _prune("research_trace.jsonl", traces(), now) + _prune("day_runs.jsonl", day_runs(), now)


def _prune(name: str, rows: list, now: datetime) -> int:
    keep = [t for t in rows if (parse_iso(t.at) or now) >= now - timedelta(days=flags.TRACE_KEEP_DAYS)]
    if len(keep) == len(rows):
        return 0
    path = root() / name
    tmp = path.with_suffix(".tmp")
    tmp.write_text("".join(t.model_dump_json() + "\n" for t in keep), encoding="utf-8", newline="\n")
    os.replace(tmp, path)
    return len(rows) - len(keep)


def day_runs() -> list[DayRun]:
    return _read("day_runs.jsonl", DayRun)


def append_day_run(run: DayRun) -> None:
    _append("day_runs.jsonl", [run])


def gaps() -> list[Gap]:
    return _read("gaps.jsonl", Gap)


def append_gaps(rows: list[Gap]) -> None:
    _append("gaps.jsonl", rows)


def gap_fills() -> list[GapFill]:
    return _read("gap_fills.jsonl", GapFill)


def append_gap_fills(rows: list[GapFill]) -> None:
    _append("gap_fills.jsonl", rows)


# ── status ───────────────────────────────────────────────────────────────────────────────────────
def load_status() -> dict:
    try:
        return json.loads((root() / "status.json").read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}


def save_status(**fields: object) -> None:
    st = {**load_status(), **fields}
    path = root() / "status.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(st, indent=1, ensure_ascii=False), encoding="utf-8", newline="\n")
