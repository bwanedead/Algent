"""
AI benchmark store — an append-only result log plus a replaceable benchmark catalog and per-source status.

    <root>/results.jsonl       one Result per line, in the order learned; never edited or removed
    <root>/benchmarks.json     id -> Benchmark (the catalog as last seen; replaced atomically)
    <root>/status.json         per source: last good fetch, last error, rows parsed, newest result date, best row count
    <root>/discovery/<day>.json  the self-reported pass's record for a day (queries, pages, spend)

Root: ``ALGENT_AI_BENCHMARKS_STORE`` or ``ai_benchmarks_store``. The log is the truth; ``current`` projects "latest line per key".
A fetch appends a line for a never-seen key, or for a key whose score CHANGED (that line has ``revised=True``); an unchanged re-fetch writes
nothing (same stance as ``instruments/store``).
"""

from __future__ import annotations

import json
import os
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from pydantic import BaseModel

from .contracts import Benchmark, Result

_ENV = "ALGENT_AI_BENCHMARKS_STORE"


class AppendResult(BaseModel):
    new: int = 0
    revised: int = 0
    unchanged: int = 0


def root() -> Path:
    return Path(os.environ.get(_ENV) or "ai_benchmarks_store")


def now_iso() -> str:
    return datetime.now(UTC).isoformat(timespec="seconds")


def _write(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(text, encoding="utf-8", newline="\n")
    tmp.replace(path)


# -- results ---------------------------------------------------------------------------------------
def log() -> list[Result]:
    """Every line ever written, oldest first. A torn line is skipped, never fatal."""
    try:
        lines = (root() / "results.jsonl").read_text(encoding="utf-8").splitlines()
    except OSError:
        return []
    out = []
    for line in lines:
        if not line.strip():
            continue
        try:
            out.append(Result.model_validate_json(line))
        except ValueError:
            continue
    return out


def current(results: list[Result] | None = None) -> list[Result]:
    """The projection: the latest line per key."""
    latest = {r.key: r for r in (results if results is not None else log())}
    return list(latest.values())


def append(new: list[Result], *, existing: list[Result] | None = None) -> AppendResult:
    """Write the new and revised results; skip what is already known. A key repeated in one batch: the last wins."""
    known = {r.key: r.score for r in current(existing)}
    batch = {r.key: r for r in new}
    lines, res = [], AppendResult()
    for key, r in batch.items():
        if key not in known:
            res.new += 1
        elif r.score != known[key]:
            r, res.revised = r.model_copy(update={"revised": True}), res.revised + 1
        else:
            res.unchanged += 1
            continue
        lines.append(r.model_dump_json())
    if lines:
        path = root() / "results.jsonl"
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("a", encoding="utf-8", newline="\n") as fh:
            fh.write("\n".join(lines) + "\n")
    return res


# -- benchmarks ------------------------------------------------------------------------------------
def benchmarks() -> dict[str, Benchmark]:
    try:
        raw = json.loads((root() / "benchmarks.json").read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}
    return {k: Benchmark.model_validate(v) for k, v in raw.items()}


def save_benchmarks(found: list[Benchmark]) -> None:
    """Merge ``found`` into the catalog (a benchmark a source stops listing stays: its history is still ours)."""
    merged = benchmarks()
    merged.update({b.id: b for b in found})
    _write(root() / "benchmarks.json", json.dumps({k: v.model_dump() for k, v in sorted(merged.items())}, ensure_ascii=False, separators=(",", ":")))


# -- status ----------------------------------------------------------------------------------------
def load_status() -> dict[str, dict[str, Any]]:
    try:
        return json.loads((root() / "status.json").read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}


def save_status(source: str, **fields: Any) -> None:
    status = load_status()
    status[source] = {**status.get(source, {}), **fields}
    _write(root() / "status.json", json.dumps(status, indent=2, sort_keys=True))


# -- discovery record ------------------------------------------------------------------------------
def discovery_path(day: str) -> Path:
    return root() / "discovery" / f"{day}.json"


def load_discovery(day: str) -> dict[str, Any]:
    try:
        return json.loads(discovery_path(day).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}


def save_discovery(day: str, record: dict[str, Any]) -> None:
    _write(discovery_path(day), json.dumps(record, indent=2, ensure_ascii=False))
