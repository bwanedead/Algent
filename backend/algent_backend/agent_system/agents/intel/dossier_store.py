"""
Reading the desk's stores for the dossiers (``dossier.py`` itself is pure).

One place that knows where each input lives under ``intel_store/``: daily reports, briefs, heat boards
(newest first, read lazily), the theater registry, the forecast ledger, the primers, and (when a Pulse store
is given) the Pulse catalog. Nothing here writes.
"""

from __future__ import annotations

import json
import re
from collections.abc import Callable, Iterator
from pathlib import Path
from typing import Any

from . import dossier, forecasts, geo, primers

_DATED = re.compile(r"^\d{4}-\d{2}-\d{2}$")


def _json(path: Path) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None


def _records(folder: Path, *, dated: bool = False) -> list[dict]:
    rows = [_json(p) for p in sorted(folder.glob("*.json")) if not dated or _DATED.match(p.stem)] \
        if folder.is_dir() else []
    return [r for r in rows if isinstance(r, dict)]


def boards_newest_first(intel_dir: Path) -> Iterator[dict]:
    """Heat boards, newest first, read one at a time (the caller stops when it has what it needs)."""
    for path in sorted((intel_dir / "boards").glob("*.json"), reverse=True) if (intel_dir / "boards").is_dir() else []:
        board = _json(path)
        if isinstance(board, dict):
            yield board


def read_inputs(intel_dir: Path, store: Any = None,
                countries: list | Callable[[], list | None] | None = geo.load) -> dossier.Inputs:
    """Everything ``dossier.build_all`` needs. ``store`` is the Pulse store (None: Pulse values fall back to
    the daily rows). ``countries`` is the basemap or a loader, called only when a dossier has places."""
    from algent_backend.agent_system.agents.pulse import registry as pulse_registry

    reports = [r for folder in sorted((intel_dir / "daily").glob("*")) if folder.is_dir()
               for r in _records(folder, dated=True)]
    registry = _json(intel_dir / "theaters.json")
    return dossier.Inputs(
        reports=reports, briefs=_records(intel_dir / "briefs"), boards=boards_newest_first(intel_dir),
        registry=registry if isinstance(registry, dict) else {}, forecasts=forecasts.current(intel_dir),
        pulses=pulse_registry.catalog(store) if store is not None else None,
        primers=primers.load(intel_dir), countries=countries)


def build(intel_dir: Path, store: Any = None, **kwargs: Any) -> dict:
    """Read the stores and build every dossier plus the index (see ``dossier.build_all``)."""
    return dossier.build_all(read_inputs(intel_dir, store, **kwargs))


def describe(intel_dir: Path, theater_ids: list[str]) -> list[dict]:
    """What the primer writer is told about each theater: ``{id, name, description, why}`` from the theater
    registry and the newest board that carries it."""
    registry = _json(intel_dir / "theaters.json") or {}
    found = dossier.newest_board_rows(boards_newest_first(intel_dir), set(theater_ids))
    out = []
    for tid in theater_ids:
        reg, meta = registry.get(tid, {}), (found.get(tid) or {}).get("theater", {})
        out.append({"id": tid, "name": reg.get("name") or meta.get("name") or tid,
                    "description": reg.get("description") or meta.get("description", ""), "why": meta.get("why", "")})
    return out
