"""
``ensure_t0`` — produce (or reuse) the t0 discovery pool programmatically.

So a discovery *run* can source its own t0 instead of a human/agent running the
ingest commands by hand. Reuses a recent pool if one exists (GKG publishes every
15 min, so a pool a few minutes old is current); otherwise fetches the latest GKG
batch, builds the insights, and consolidates the pool — all free (GDELT bulk), all
narrated through ``on_progress`` so the caller can surface it in a run timeline.

Velocity comes from the rolling memory, which persists across runs, so even the
fast (no-warmup) path sharpens over repeated runs.
"""

from __future__ import annotations

import json
import time
from collections.abc import Callable
from pathlib import Path
from typing import Any

from algent_backend.data_ingestion.cli._shared import (
    beats_dir,
    insights_dir,
    latest_file,
    memory_dir,
    pool_dir,
    prune_files,
)

from ..sources import gdelt_gkg
from .insights import build_insights
from .memory import load_memory, save_memory
from .pool import build_pool
from .report import BeatSheet

DEFAULT_FRESH_MINUTES = 20  # a pool newer than this is current (GKG is 15-min)
_KEEP = 1

ProgressFn = Callable[[str], None]


def ensure_t0(
    *, source: str = "gdelt_gkg", fresh_minutes: float = DEFAULT_FRESH_MINUTES,
    on_progress: ProgressFn | None = None,
) -> tuple[dict[str, Any], str]:
    """Return ``(pool_dict, pool_path)`` — a fresh-enough t0, producing it if needed."""
    say = on_progress or (lambda _m: None)

    existing = latest_file(pool_dir(), "pool_*.json")
    if existing is not None and _age_minutes(existing) <= fresh_minutes:
        say(f"reusing current t0 pool ({_age_minutes(existing):.0f} min old)")
        return json.loads(existing.read_text(encoding="utf-8")), str(existing)

    say("no fresh t0 — building one (free GDELT)…")
    report = _build_insights(source, say)
    pool, path = _build_pool(report, say)
    return pool, path


def _build_insights(source: str, say: ProgressFn):
    say("fetching latest GKG batch (download)…")
    batch_id, records = gdelt_gkg.fetch_latest()
    say(f"GKG batch {batch_id}: {len(records)} records")
    memory = load_memory(source, memory_dir())
    report, counts = build_insights(records, source=source, batch_id=batch_id, memory=memory)
    out = insights_dir()
    out.mkdir(parents=True, exist_ok=True)
    (out / f"{source}_{batch_id}.json").write_text(report.model_dump_json(indent=2), encoding="utf-8")
    save_memory(memory.with_batch(batch_id, counts), memory_dir())
    prune_files(out, f"{source}_*.json", keep=_KEEP)
    say(f"insights: {len(report.candidates)} candidates across {len(report.by_language)} languages")
    return report


def _build_pool(report, say: ProgressFn) -> tuple[dict[str, Any], str]:
    sheet = None
    beats_latest = latest_file(beats_dir(), "beats_*.json")
    if beats_latest is not None:
        try:
            sheet = BeatSheet.model_validate_json(beats_latest.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            sheet = None
    pool = build_pool(report, sheet)
    out = pool_dir()
    out.mkdir(parents=True, exist_ok=True)
    path = out / f"pool_{report.batch_id}.json"
    path.write_text(pool.model_dump_json(indent=2), encoding="utf-8")
    prune_files(out, "pool_*.json", keep=_KEEP)
    say(f"t0 pool ready: {pool.item_count} items")
    return pool.model_dump(), str(path)


def _age_minutes(path: Path) -> float:
    return (time.time() - path.stat().st_mtime) / 60.0
