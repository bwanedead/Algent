"""
Elections store on disk — append-only snapshots, one file per election.

    <root>/snapshots/<slug>.jsonl   one Snapshot per line, appended only when what the pages said changed (``Snapshot.digest``); never rewritten
    <root>/status.json              last run: when, how many elections read, appended, errors

Root: ``ALGENT_ELECTIONS_STORE`` or ``elections_store``. A line is a few KB to ~30 KB (the newest polls per table, the results table), so the store grows with
how often an election's pages change, not with how often we look. History is the point: the as-of record of what the polls said on each day.
"""

from __future__ import annotations

import json
import os
from datetime import UTC, datetime
from pathlib import Path

from .contracts import Snapshot

_ENV = "ALGENT_ELECTIONS_STORE"


def root() -> Path:
    return Path(os.environ.get(_ENV) or "elections_store")


def now_iso() -> str:
    return datetime.now(UTC).isoformat(timespec="seconds")


def _path(slug: str) -> Path:
    return root() / "snapshots" / f"{slug}.jsonl"


def slugs() -> list[str]:
    d = root() / "snapshots"
    return sorted(p.stem for p in d.glob("*.jsonl")) if d.is_dir() else []


def snapshots(slug: str) -> list[Snapshot]:
    """Every snapshot of an election, oldest first; a torn line is skipped, never hides the rest."""
    try:
        lines = _path(slug).read_text(encoding="utf-8").splitlines()
    except OSError:
        return []
    out = []
    for line in lines:
        try:
            out.append(Snapshot.model_validate_json(line))
        except ValueError:
            continue
    return out


def latest(slug: str) -> Snapshot | None:
    rows = snapshots(slug)
    return rows[-1] if rows else None


def latest_all() -> list[Snapshot]:
    return [s for s in (latest(slug) for slug in slugs()) if s is not None]


def append(snap: Snapshot) -> bool:
    """Add a snapshot unless it says what the election's newest one already says (then nothing is written). Returns whether a line was added."""
    last = latest(snap.slug)
    if last is not None and last.digest() == snap.digest():
        return False
    path = _path(snap.slug)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8", newline="\n") as fh:
        fh.write(snap.model_dump_json(by_alias=True) + "\n")
    return True


def load_status() -> dict:
    try:
        return json.loads((root() / "status.json").read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}


def save_status(**fields: object) -> None:
    path = root() / "status.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps({**load_status(), **fields}, indent=1, ensure_ascii=False), encoding="utf-8", newline="\n")
