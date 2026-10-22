"""
Satellite store: what a pass keeps on disk, under ``<live root>/satellite/`` (the live store: ``ALGENT_LIVE_STORE`` or ``live_store``).

    records.jsonl              APPEND-ONLY: one line per site per pass (what was seen, the verdicts and their provenance). Never rewritten.
    watch.json                 the ranked watch list of the last pass
    doc.json                   the last built document (the same JSON that is published)
    sites/<id>/baseline.png    the baseline chip (true colour) and its scene-classification chip ``baseline_scl.png``
    sites/<id>/last.png        the latest chip and ``last_scl.png`` (kept to compare the next scene against)
    chips/<id>/<file>.png      dated chips published to Storage (the baseline's and the newest few scenes'), kept so a pass can re-upload them

Chips are 256 px PNGs of ~150 kB; the chip folder is pruned to ``KEEP_DATED`` newest scenes per site plus the baseline's.
"""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any, Iterable

from algent_backend.live import store as live_store

KEEP_DATED = 3


def root() -> Path:
    return live_store.root() / "satellite"


def _atomic(path: Path, data: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_bytes(data)
    os.replace(tmp, path)


def write_json(name: str, doc: Any) -> None:
    _atomic(root() / name, json.dumps(doc, separators=(",", ":"), ensure_ascii=False).encode("utf-8"))


def read_json(name: str, default: Any = None) -> Any:
    try:
        return json.loads((root() / name).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return default


def write_bytes(rel: str, data: bytes) -> None:
    _atomic(root() / rel, data)


def read_bytes(rel: str) -> bytes | None:
    try:
        return (root() / rel).read_bytes()
    except OSError:
        return None


def append_record(rec: dict[str, Any]) -> None:
    path = root() / "records.jsonl"
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8", newline="\n") as f:
        f.write(json.dumps(rec, separators=(",", ":"), ensure_ascii=False) + "\n")


def records(site: str | None = None) -> list[dict[str, Any]]:
    """Every record (oldest first), optionally one site's. A torn line is skipped."""
    out: list[dict[str, Any]] = []
    try:
        lines: Iterable[str] = (root() / "records.jsonl").read_text(encoding="utf-8").splitlines()
    except OSError:
        return out
    for line in lines:
        try:
            r = json.loads(line)
        except ValueError:
            continue
        if site is None or r.get("site_id") == site:
            out.append(r)
    return out


def prune_chips(site: str, keep: set[str]) -> None:
    """Delete dated chips of a site that are not in ``keep`` (file names)."""
    d = root() / "chips" / site
    if not d.is_dir():
        return
    for p in d.glob("*.png"):
        if p.name not in keep:
            try:
                p.unlink()
            except OSError:
                pass
