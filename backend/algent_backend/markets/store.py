"""
Markets store on disk. Root: ``ALGENT_MARKETS_STORE`` or ``markets_store``. Everything is append-only JSON lines: history is never rewritten,
so the record cannot be quietly improved after the fact.

    markets.jsonl     one Market REVISION per line (a changed market is a new line; the last line of an id wins)
    snapshots.jsonl   one price Snapshot per line (live passes and the CLOB history backfill)
    forecasts.jsonl   one Forecast per line: OURS, immutable once written
    trades.jsonl      paper trades: open / mark / settle (a position is a projection of its lines)
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
from .contracts import Forecast, Market, Snapshot, Trade

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
