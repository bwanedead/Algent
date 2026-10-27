"""
The acquisition ledger (experiment framework L1): when WE first held each source unit, append-only, outside every rebuildable store.

The corpus index is derived and a full rebuild resets its ``ingested_at``, so it cannot say when a document reached us. This ledger can: one line per
(unit key, content fingerprint), written the first time a corpus build sees that content, never rewritten, never reset by a rebuild.

    <ALGENT_ACQUISITION_STORE or acquisition_store>/ledger.jsonl
    {"key": "daily:geopolitics:2026-10-05", "fp": "<content hash>", "product": "dailies", "source": "dailies", "date": "2026-10-05",
     "first_seen": "<ISO instant of the build that first saw it>", "backfill": false}

Honesty rules. ``first_seen`` is the build that first saw the content: an UPPER bound on when we acquired it (we held it no later), never a guess that it was earlier.
The first build against an empty ledger indexes a record that already existed, so every unit it sees is ``backfill: true``: its acquisition time is unknown, not "now".
A changed unit is a new (key, fp) entry: the body now in the index was not held before that entry, whatever the older version said.
"""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

ENV = "ALGENT_ACQUISITION_STORE"
DEFAULT_DIR = "acquisition_store"
LEDGER = "ledger.jsonl"
Key = tuple[str, str]               # (unit key, content fingerprint)


def root() -> Path:
    return Path(os.environ.get(ENV) or DEFAULT_DIR)


def _file() -> Path:
    return root() / LEDGER


def load() -> dict[Key, dict[str, Any]]:
    """Every entry by (key, fp). A malformed line is skipped, never fatal."""
    out: dict[Key, dict[str, Any]] = {}
    try:
        lines = _file().read_text(encoding="utf-8").splitlines()
    except OSError:
        return out
    for ln in lines:
        try:
            e = json.loads(ln)
            out.setdefault((e["key"], e["fp"]), e)               # the first line for a pair stands
        except (ValueError, KeyError, TypeError):
            continue
    return out


class Ledger:
    """One build's view of the ledger: what is known at the start, and the units this build sees. ``flush`` appends the new ones in one write."""

    def __init__(self) -> None:
        self.known = load()
        self.backfill = not self.known            # decided once per build: the first build against an empty ledger indexes a record that already existed
        self.pending: list[dict[str, Any]] = []

    def add(self, key: str, fp: str, product: str = "", source: str = "", date: str = "") -> None:
        self.pending.append({"key": key, "fp": fp, "product": product, "source": source, "date": date})

    def flush(self, now: str) -> int:
        """Append the pending units not yet in the ledger. Returns lines written."""
        fresh = []
        for u in self.pending:
            k = (u["key"], u["fp"])
            if k not in self.known:
                self.known[k] = {**u, "first_seen": now, "backfill": self.backfill}
                fresh.append(self.known[k])
        self.pending = []
        if fresh:
            p = _file()
            p.parent.mkdir(parents=True, exist_ok=True)
            with p.open("a", encoding="utf-8", newline="\n") as fh:
                fh.write("".join(json.dumps(e, sort_keys=True, separators=(",", ":"), ensure_ascii=False) + "\n" for e in fresh))
        return len(fresh)


def acquired_at(entry: dict[str, Any] | None) -> str:
    """The instant we are SURE we held the content by, or '' when unknown (no entry, or a backfill entry)."""
    return "" if entry is None or entry.get("backfill") else str(entry["first_seen"])
