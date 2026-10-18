"""
Flows store — what the lane tracker and the trade refresh keep on disk. Small by design (the server has 4 GB and the database is shared).

    <live root>/flows/tracker.json.gz   per vessel: the place it was last in and when ({mmsi: [place, ts]}); bounded, replaced atomically
    <live root>/flows/days.json         the daily aggregates (lane hops, place visits, hours watched) and the hop-duration samples
    <live root>/flows/trade.json        the last fetched commodity and money picture (``trade/``) with when it was fetched

Root: the live store (``ALGENT_LIVE_STORE`` or ``live_store``), like the other things the always-on stream service writes and the
timers read. Aggregates only: no raw tracks, no per-vessel history beyond the one last place.
"""

from __future__ import annotations

import gzip
import json
import os
from pathlib import Path
from typing import Any

from algent_backend.live import store as live_store


def root() -> Path:
    return live_store.root() / "flows"


def _write_text(path: Path, text: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_bytes(text)
    os.replace(tmp, path)


def write_json(name: str, doc: Any, *, gz: bool = False) -> None:
    raw = json.dumps(doc, separators=(",", ":"), ensure_ascii=False).encode("utf-8")
    _write_text(root() / name, gzip.compress(raw, compresslevel=5, mtime=0) if gz else raw)


def read_json(name: str, default: Any = None) -> Any:
    path = root() / name
    try:
        raw = path.read_bytes()
        if raw[:2] == b"\x1f\x8b":
            raw = gzip.decompress(raw)
        return json.loads(raw.decode("utf-8"))
    except (OSError, ValueError, EOFError):
        return default
