"""Load t0/t1 lines as optional warrant hints. Empty string if nothing is on disk."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any


def discovery_brief(*, pool: dict[str, Any] | None = None,
                    portfolio: dict[str, Any] | None = None,
                    limit: int = 24) -> str:
    """Short lines the warrant can read. Empty string if nothing is on disk."""
    half = max(4, limit // 2)
    lines = _pool_lines(pool if pool is not None else _load_pool(), half)
    lines += _portfolio_lines(
        portfolio if portfolio is not None else _load_portfolio(), half)
    return "\n".join(lines)


def _load_pool() -> dict[str, Any]:
    try:
        from algent_backend.data_ingestion.newsroom.discovery.pipeline import pool_dir
        files = sorted(Path(pool_dir()).glob("pool_*.json"), key=lambda p: p.stat().st_mtime)
    except Exception:  # noqa: BLE001 — missing ingest is a seed miss, not a crash
        return {}
    return _newest_json(files)


def _load_portfolio() -> dict[str, Any]:
    try:
        from algent_backend.agent_system.runs.control_plane.layout import runs_data_root
        files = sorted(
            Path(runs_data_root()).glob(
                "discovery_synthesis/*/artifacts/research_portfolio.json"),
            key=lambda p: p.stat().st_mtime,
        )
    except Exception:  # noqa: BLE001
        return {}
    return _newest_json(files)


def _newest_json(files: list[Path]) -> dict[str, Any]:
    if not files:
        return {}
    try:
        data = json.loads(files[-1].read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    return data if isinstance(data, dict) else {}


def _pool_lines(pool: dict[str, Any], n: int) -> list[str]:
    out: list[str] = []
    for item in (pool.get("items") or [])[:n]:
        if not isinstance(item, dict):
            continue
        label = str(item.get("label") or "").strip()
        if label:
            out.append(f"- pool: {label[:160]}")
    return out


def _portfolio_lines(portfolio: dict[str, Any], n: int) -> list[str]:
    out: list[str] = []
    for vec in (portfolio.get("vectors") or [])[:n]:
        if not isinstance(vec, dict):
            continue
        title = str(vec.get("title") or "").strip()
        thesis = str(vec.get("thesis") or "").strip()
        line = title or thesis
        if line:
            out.append(f"- menu: {line[:160]}")
    return out
